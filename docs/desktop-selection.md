# GNOME Shell workflow

Install `ab-proofread`, then enable the optional GNOME Shell extension
`ab_proofread@ab.local` with GNOME Extensions. The package never enables it
or modifies session settings automatically; a fresh login may be needed for
GNOME to discover a newly installed system extension.

Select text in an editable field that exposes an unambiguous selection through
AT-SPI. A contextual icon appears near the pointer. Clicking it checks Russian
text locally. With no findings it briefly says «Отлично! Ошибок не найдено.»;
otherwise it shows the available correction or a short status. The top-bar
control reports status and pauses/resumes the watcher. The selection is read
only after the explicit click; the icon can therefore appear on non-Russian
selections, which are not checked. Nothing is automatically replaced. The preview is not a claim of
cross-application Replace support; that requires a separately shipped and
verified app-side native adapter, which this package does not include.

The extension depends on target application accessibility behavior. Password
fields, terminals and code editors are excluded where identifiable. No browser
extension, standalone GTK window, keyboard hook or clipboard polling is shipped.
