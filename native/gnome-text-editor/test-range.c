/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <gtk/gtk.h>
#include "ab_proofread-range.h"

static void
set_selection (GtkTextBuffer *buffer, int start, int end)
{
  GtkTextIter a, b;
  gtk_text_buffer_get_iter_at_offset (buffer, &a, start);
  gtk_text_buffer_get_iter_at_offset (buffer, &b, end);
  gtk_text_buffer_select_range (buffer, &a, &b);
}

static char *
contents (GtkTextBuffer *buffer)
{
  GtkTextIter a, b;
  gtk_text_buffer_get_bounds (buffer, &a, &b);
  return gtk_text_buffer_get_text (buffer, &a, &b, TRUE);
}

static void
test_undo (void)
{
  g_autoptr(GtkTextBuffer) buffer = gtk_text_buffer_new (NULL);
  g_autofree char *after = NULL;
  g_autofree char *undone = NULL;
  gtk_text_buffer_set_text (buffer, "🙂 ашибка / speling!", -1);
  gtk_text_buffer_set_enable_undo (buffer, TRUE);
  set_selection (buffer, 2, 18);
  g_assert_true (ab_proofread_replace_range (buffer, 2, 18, "ашибка / speling", "ошибка / spelling"));
  after = contents (buffer);
  g_assert_cmpstr (after, ==, "🙂 ошибка / spelling!");
  gtk_text_buffer_undo (buffer);
  undone = contents (buffer);
  g_assert_cmpstr (undone, ==, "🙂 ашибка / speling!");
}

static void
test_stale_range (void)
{
  g_autoptr(GtkTextBuffer) buffer = gtk_text_buffer_new (NULL);
  g_autofree char *after = NULL;
  gtk_text_buffer_set_text (buffer, "speling speling", -1);
  gtk_text_buffer_set_enable_undo (buffer, TRUE);
  set_selection (buffer, 8, 15);
  g_assert_false (ab_proofread_replace_range (buffer, 0, 7, "speling", "spelling"));
  after = contents (buffer);
  g_assert_cmpstr (after, ==, "speling speling");
  g_assert_false (gtk_text_buffer_get_can_undo (buffer));
}

int main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/ab_proofread/range/undo", test_undo);
  g_test_add_func ("/ab_proofread/range/stale", test_stale_range);
  return g_test_run ();
}
