/* Multi-format clipboard source for GNOME 50.5. GJS cannot implement
 * MetaSelectionSource.read_async because its vfunc includes a callback. */
#include <gio/gio.h>
#include <meta/meta-selection-source.h>

typedef struct { MetaSelectionSource parent; GHashTable *contents; } WayStrokeClipboardSource;
typedef struct { MetaSelectionSourceClass parent; } WayStrokeClipboardSourceClass;
G_DEFINE_TYPE(WayStrokeClipboardSource, waystroke_clipboard_source, META_TYPE_SELECTION_SOURCE)
static guint read_signal;

static GList *get_mimetypes(MetaSelectionSource *source) {
    GList *types=NULL;GHashTableIter iter;gpointer key;
    g_hash_table_iter_init(&iter,((WayStrokeClipboardSource *)source)->contents);
    while(g_hash_table_iter_next(&iter,&key,NULL))types=g_list_prepend(types,g_strdup(key));
    return g_list_reverse(types);
}
static void read_async(MetaSelectionSource *source,const char *mimetype,GCancellable *cancellable,GAsyncReadyCallback callback,gpointer user_data) {
    GTask *task=g_task_new(source,cancellable,callback,user_data);
    GBytes *bytes=g_hash_table_lookup(((WayStrokeClipboardSource *)source)->contents,mimetype);
    if(!bytes)g_task_return_new_error(task,G_IO_ERROR,G_IO_ERROR_NOT_SUPPORTED,"Clipboard does not contain %s",mimetype);
    else {g_task_return_pointer(task,g_memory_input_stream_new_from_bytes(bytes),g_object_unref);g_signal_emit(source,read_signal,0,mimetype);}
    g_object_unref(task);
}
static GInputStream *read_finish(MetaSelectionSource *source,GAsyncResult *result,GError **error) {
    g_return_val_if_fail(g_task_is_valid(result,source),NULL);return g_task_propagate_pointer(G_TASK(result),error);
}
static void finalize(GObject *object) {
    g_hash_table_unref(((WayStrokeClipboardSource *)object)->contents);
    G_OBJECT_CLASS(waystroke_clipboard_source_parent_class)->finalize(object);
}
static void waystroke_clipboard_source_class_init(WayStrokeClipboardSourceClass *klass) {
    G_OBJECT_CLASS(klass)->finalize=finalize;
    MetaSelectionSourceClass *source=META_SELECTION_SOURCE_CLASS(klass);
    source->get_mimetypes=get_mimetypes;source->read_async=read_async;source->read_finish=read_finish;
    read_signal=g_signal_new("read",G_TYPE_FROM_CLASS(klass),G_SIGNAL_RUN_LAST,0,NULL,NULL,NULL,G_TYPE_NONE,1,G_TYPE_STRING);
}
static void waystroke_clipboard_source_init(WayStrokeClipboardSource *source) {
    source->contents=g_hash_table_new_full(g_str_hash,g_str_equal,g_free,(GDestroyNotify)g_bytes_unref);
}
GObject *waystroke_clipboard_source_new(GVariant *contents) {
    g_return_val_if_fail(g_variant_is_of_type(contents,G_VARIANT_TYPE("a{say}")),NULL);
    WayStrokeClipboardSource *source=g_object_new(waystroke_clipboard_source_get_type(),NULL);
    GVariantIter iter;const char *name;GVariant *value;
    g_variant_iter_init(&iter,contents);
    while(g_variant_iter_next(&iter,"{&s@ay}",&name,&value)) {
        gsize size;const void *bytes=g_variant_get_fixed_array(value,&size,1);
        g_hash_table_insert(source->contents,g_strdup(name),g_bytes_new(bytes,size));g_variant_unref(value);
    }
    return G_OBJECT(source);
}
