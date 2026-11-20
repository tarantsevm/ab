/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <gtk/gtk.h>

static inline gboolean
ab_proofread_replace_range (GtkTextBuffer *buffer, int start, int end,
                       const char *original, const char *replacement)
{
  GtkTextIter a, b;
  g_autofree char *current = NULL;
  if (start < 0 || end <= start || end - start > 20000 ||
      !gtk_text_buffer_get_enable_undo (buffer) ||
      !g_utf8_validate (replacement, -1, NULL) ||
      g_utf8_strlen (replacement, -1) > 20000 ||
      !gtk_text_buffer_get_selection_bounds (buffer, &a, &b) ||
      gtk_text_iter_get_offset (&a) != start || gtk_text_iter_get_offset (&b) != end)
    return FALSE;
  current = gtk_text_buffer_get_slice (buffer, &a, &b, TRUE);
  if (strcmp (current, original) != 0 || strcmp (current, replacement) == 0)
    return FALSE;
  /* In-process, non-yielding, one undo record. Only used on a plain editor. */
  gtk_text_buffer_begin_user_action (buffer);
  gtk_text_buffer_delete (buffer, &a, &b);
  gtk_text_buffer_insert (buffer, &a, replacement, -1);
  gtk_text_buffer_end_user_action (buffer);
  return TRUE;
}
