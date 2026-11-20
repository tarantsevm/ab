/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once

#include <unistd.h>
#include "editor-page-private.h"
#include "editor-window.h"
#include "ab_proofread-range.h"

#define AB_PROOFREAD_IFACE "local.ab_proofread.TextEditor1"
#define AB_PROOFREAD_PATH "/local/ab_proofread/TextEditor1"

static const char ab_proofread_xml[] =
  "<node><interface name='" AB_PROOFREAD_IFACE "'>"
  "<method name='Prepare'>"
  "<arg type='i' direction='in'/><arg type='i' direction='in'/><arg type='s' direction='in'/>"
  "<arg type='s' direction='out'/><arg type='x' direction='out'/></method>"
  "<method name='Replace'>"
  "<arg type='s' direction='in'/><arg type='s' direction='in'/><arg type='x' direction='in'/>"
  "<arg type='b' direction='out'/></method></interface></node>";

typedef struct {
  GtkApplication *app;
  GDBusConnection *bus;
  guint registration, name_owner, timeout;
  GtkWindow *window;
  EditorPage *page;
  GtkTextView *view;
  GtkTextBuffer *buffer;
  int start, end;
  gint64 expires;
  char *sender, *token, *original;
} AbProofreadEndpoint;

static void
ab_proofread_forget (AbProofreadEndpoint *self)
{
  if (self->window) g_signal_handlers_disconnect_by_data (self->window, self);
  if (self->page) g_signal_handlers_disconnect_by_data (self->page, self);
  if (self->view) g_signal_handlers_disconnect_by_data (self->view, self);
  if (self->buffer) g_signal_handlers_disconnect_by_data (self->buffer, self);
  g_clear_handle_id (&self->timeout, g_source_remove);
  g_clear_object (&self->window);
  g_clear_object (&self->page);
  g_clear_object (&self->view);
  g_clear_object (&self->buffer);
  g_clear_pointer (&self->sender, g_free);
  g_clear_pointer (&self->token, g_free);
  g_clear_pointer (&self->original, g_free);
  self->expires = 0;
}

static gboolean
ab_proofread_expire (gpointer data)
{
  AbProofreadEndpoint *self = data;
  self->timeout = 0;
  ab_proofread_forget (self);
  return G_SOURCE_REMOVE;
}

static void
ab_proofread_context_changed (GObject *object, GParamSpec *property, AbProofreadEndpoint *self)
{
  /* Invalidate immediately; release refs/handlers outside the signal. */
  self->expires = 0;
}

static void
ab_proofread_buffer_changed (GtkTextBuffer *buffer, AbProofreadEndpoint *self)
{
  self->expires = 0;
}

static void
ab_proofread_mark_changed (GtkTextBuffer *buffer, GtkTextIter *iter, GtkTextMark *mark,
                      AbProofreadEndpoint *self)
{
  if (mark == gtk_text_buffer_get_insert (buffer) ||
      mark == gtk_text_buffer_get_selection_bound (buffer))
    self->expires = 0;
}

static gboolean
ab_proofread_target (AbProofreadEndpoint *self, GtkWindow **window, EditorPage **page,
                GtkTextView **view, GtkTextBuffer **buffer)
{
  *window = gtk_application_get_active_window (self->app);
  if (!EDITOR_IS_WINDOW (*window) || !gtk_window_is_active (*window))
    return FALSE;
  *page = editor_window_get_visible_page (EDITOR_WINDOW (*window));
  if (!*page || !(*page)->view)
    return FALSE;
  *view = GTK_TEXT_VIEW ((*page)->view);
  if (gtk_window_get_focus (*window) != GTK_WIDGET (*view) ||
      !gtk_widget_has_focus (GTK_WIDGET (*view)) || !gtk_text_view_get_editable (*view))
    return FALSE;
  *buffer = gtk_text_view_get_buffer (*view);
  return *buffer == GTK_TEXT_BUFFER (editor_page_get_document (*page)) &&
         gtk_text_buffer_get_enable_undo (*buffer);
}

static void
ab_proofread_method (GDBusConnection *bus, const char *sender, const char *path,
                const char *interface, const char *method, GVariant *params,
                GDBusMethodInvocation *invocation, gpointer data)
{
  AbProofreadEndpoint *self = data;
  GtkWindow *window;
  EditorPage *page;
  GtkTextView *view;
  GtkTextBuffer *buffer;
  gint64 now = g_get_monotonic_time ();

  if (strcmp (method, "Prepare") == 0)
    {
      GtkTextIter a, b;
      int start, end;
      const char *original;
      g_autofree char *current = NULL;
      g_variant_get (params, "(ii&s)", &start, &end, &original);
      ab_proofread_forget (self);
      if (start < 0 || end <= start || end - start > 20000 ||
          strlen (original) > 80000 || !ab_proofread_target (self, &window, &page, &view, &buffer) ||
          !gtk_text_buffer_get_selection_bounds (buffer, &a, &b) ||
          gtk_text_iter_get_offset (&a) != start || gtk_text_iter_get_offset (&b) != end)
        goto no_offer;
      current = gtk_text_buffer_get_slice (buffer, &a, &b, TRUE);
      if (strcmp (current, original) != 0)
        goto no_offer;
      self->window = g_object_ref (window);
      self->page = g_object_ref (page);
      self->view = g_object_ref (view);
      self->buffer = g_object_ref (buffer);
      self->start = start;
      self->end = end;
      self->original = g_steal_pointer (&current);
      self->sender = g_strdup (sender);
      self->token = g_uuid_string_random ();
      self->expires = now + 45 * G_USEC_PER_SEC;
      self->timeout = g_timeout_add_seconds (45, ab_proofread_expire, self);
      g_signal_connect (window, "notify::is-active", G_CALLBACK (ab_proofread_context_changed), self);
      g_signal_connect (window, "notify::focus-widget", G_CALLBACK (ab_proofread_context_changed), self);
      g_signal_connect (window, "notify::visible-page", G_CALLBACK (ab_proofread_context_changed), self);
      g_signal_connect (view, "notify::buffer", G_CALLBACK (ab_proofread_context_changed), self);
      g_signal_connect (view, "notify::editable", G_CALLBACK (ab_proofread_context_changed), self);
      g_signal_connect (buffer, "changed", G_CALLBACK (ab_proofread_buffer_changed), self);
      g_signal_connect (buffer, "mark-set", G_CALLBACK (ab_proofread_mark_changed), self);
      g_dbus_method_invocation_return_value (invocation, g_variant_new ("(sx)", self->token, self->expires));
      return;
    no_offer:
      g_dbus_method_invocation_return_value (invocation, g_variant_new ("(sx)", "", (gint64)0));
    }
  else if (strcmp (method, "Replace") == 0)
    {
      const char *token, *replacement;
      gint64 deadline;
      gboolean changed = FALSE;
      g_variant_get (params, "(&s&sx)", &token, &replacement, &deadline);
      if (self->token && g_str_equal (sender, self->sender) && g_str_equal (token, self->token))
        {
          /* Consume before editing, even if this attempt must be refused. */
          g_clear_pointer (&self->token, g_free);
          if (now < self->expires && now < deadline && deadline <= self->expires &&
              strlen (replacement) <= 80000 &&
              ab_proofread_target (self, &window, &page, &view, &buffer) &&
              window == self->window && page == self->page && view == self->view && buffer == self->buffer)
            changed = ab_proofread_replace_range (buffer, self->start, self->end, self->original, replacement);
          ab_proofread_forget (self);
        }
      g_dbus_method_invocation_return_value (invocation, g_variant_new ("(b)", changed));
    }
}

static void
ab_proofread_shutdown (gpointer data)
{
  AbProofreadEndpoint *self = data;
  ab_proofread_forget (self);
  if (self->name_owner) g_bus_unown_name (self->name_owner);
  if (self->registration) g_dbus_connection_unregister_object (self->bus, self->registration);
  g_object_unref (self->bus);
  g_free (self);
}

static void
ab_proofread_startup (GApplication *app, gpointer unused)
{
  static const GDBusInterfaceVTable vtable = { .method_call = ab_proofread_method };
  g_autoptr(GDBusNodeInfo) node = NULL;
  g_autofree char *name = NULL;
  GDBusConnection *bus = g_application_get_dbus_connection (app);
  AbProofreadEndpoint *self;

  if (!bus || getuid () == 0 || g_strcmp0 (g_getenv ("AB_PROOFREAD_TEXT_EDITOR"), "1") != 0)
    return;
  node = g_dbus_node_info_new_for_xml (ab_proofread_xml, NULL);
  if (!node) return;
  self = g_new0 (AbProofreadEndpoint, 1);
  self->app = GTK_APPLICATION (app);
  self->bus = g_object_ref (bus);
  self->registration = g_dbus_connection_register_object (bus, AB_PROOFREAD_PATH, node->interfaces[0],
                                                           &vtable, self, NULL, NULL);
  if (!self->registration)
    {
      ab_proofread_shutdown (self);
      return;
    }
  name = g_strdup_printf (AB_PROOFREAD_IFACE ".p%lu", (unsigned long)getpid ());
  self->name_owner = g_bus_own_name_on_connection (bus, name, G_BUS_NAME_OWNER_FLAGS_DO_NOT_QUEUE,
                                                   NULL, NULL, NULL, NULL);
  g_object_set_data_full (G_OBJECT (app), "ab_proofread-endpoint", self, ab_proofread_shutdown);
}
