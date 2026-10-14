/* Multi-format clipboard source for GNOME 50.5. GJS cannot implement
 * MetaSelectionSource.read_async because its vfunc includes a callback. */
#include <gio/gio.h>
#include <meta/meta-selection-source.h>
#include <clutter/clutter.h>

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

/* Observe transfer requests without replacing owners or reading contents. */
typedef void (*ReadAsync)(MetaSelectionSource *,const char *,GCancellable *,GAsyncReadyCallback,gpointer);
typedef struct { MetaSelectionSourceClass *klass;ReadAsync original;guint users; } ReadHook;
typedef struct { GObject parent;GHashTable *types; } WayStrokeClipboardWatch;
typedef struct { GObjectClass parent; } WayStrokeClipboardWatchClass;
G_DEFINE_TYPE(WayStrokeClipboardWatch,waystroke_clipboard_watch,G_TYPE_OBJECT)
static GHashTable *read_hooks;
static GList *source_watches;
static guint requested_signal;
static void observed_read_async(MetaSelectionSource *source,const char *mime,GCancellable *cancel,GAsyncReadyCallback callback,gpointer data) {
    gpointer type=GSIZE_TO_POINTER(G_OBJECT_TYPE(source));
    ReadHook *hook=g_hash_table_lookup(read_hooks,type);ReadAsync original=hook->original;
    for(GList *item=source_watches;item;item=item->next) {
        WayStrokeClipboardWatch *watch=item->data;
        if(g_hash_table_contains(watch->types,type))g_signal_emit(watch,requested_signal,0);
    }
    original(source,mime,cancel,callback,data);
}
static void watch_type(WayStrokeClipboardWatch *watch,GType type) {
    gpointer key=GSIZE_TO_POINTER(type);
    if(g_hash_table_contains(watch->types,key))return;
    ReadHook *hook=g_hash_table_lookup(read_hooks,key);
    if(!hook) {
        hook=g_new0(ReadHook,1);hook->klass=g_type_class_ref(type);hook->original=hook->klass->read_async;
        if(hook->original==observed_read_async) {
            for(GType parent=g_type_parent(type);parent;parent=g_type_parent(parent)) {
                ReadHook *inherited=g_hash_table_lookup(read_hooks,GSIZE_TO_POINTER(parent));
                if(inherited){hook->original=inherited->original;break;}
            }
        }
        if(!hook->original){g_type_class_unref(hook->klass);g_free(hook);return;}
        hook->klass->read_async=observed_read_async;g_hash_table_insert(read_hooks,key,hook);
    }
    hook->users++;g_hash_table_add(watch->types,key);
}
static void watch_children(WayStrokeClipboardWatch *watch,GType parent) {
    guint count;GType *types=g_type_children(parent,&count);
    for(guint index=0;index<count;index++) {
        if(!g_type_test_flags(types[index],G_TYPE_FLAG_ABSTRACT))watch_type(watch,types[index]);
        watch_children(watch,types[index]);
    }
    g_free(types);
}
void waystroke_clipboard_watch_add_source(GObject *object,GObject *source) {
    g_return_if_fail(META_IS_SELECTION_SOURCE(source));
    watch_type((WayStrokeClipboardWatch *)object,G_OBJECT_TYPE(source));
}
void waystroke_clipboard_watch_stop(GObject *object) {
    WayStrokeClipboardWatch *watch=(WayStrokeClipboardWatch *)object;
    source_watches=g_list_remove(source_watches,watch);
    GHashTableIter iter;gpointer type;g_hash_table_iter_init(&iter,watch->types);
    while(g_hash_table_iter_next(&iter,&type,NULL)) {
        ReadHook *hook=g_hash_table_lookup(read_hooks,type);
        if(--hook->users==0) {
            hook->klass->read_async=hook->original;
            g_hash_table_remove(read_hooks,type);g_type_class_unref(hook->klass);g_free(hook);
        }
    }
    g_hash_table_remove_all(watch->types);
}
static void watch_finalize(GObject *object) {
    waystroke_clipboard_watch_stop(object);g_hash_table_unref(((WayStrokeClipboardWatch *)object)->types);
    G_OBJECT_CLASS(waystroke_clipboard_watch_parent_class)->finalize(object);
}
static void waystroke_clipboard_watch_class_init(WayStrokeClipboardWatchClass *klass) {
    G_OBJECT_CLASS(klass)->finalize=watch_finalize;
    requested_signal=g_signal_new("requested",G_TYPE_FROM_CLASS(klass),G_SIGNAL_RUN_LAST,0,NULL,NULL,NULL,G_TYPE_NONE,0);
}
static void waystroke_clipboard_watch_init(WayStrokeClipboardWatch *watch) {watch->types=g_hash_table_new(g_direct_hash,g_direct_equal);}
GObject *waystroke_clipboard_watch_new(void) {
    if(!read_hooks)read_hooks=g_hash_table_new(g_direct_hash,g_direct_equal);
    WayStrokeClipboardWatch *watch=g_object_new(waystroke_clipboard_watch_get_type(),NULL);
    watch_children(watch,META_TYPE_SELECTION_SOURCE);source_watches=g_list_append(source_watches,watch);return G_OBJECT(watch);
}

/* GNOME 50.5 exports this constructor from libmutter-clutter, but omits it
 * from the installed header. ABI: clutter/clutter/clutter-event-private.h.
 * Preserve all original modifiers and bypass seat-wide pressed-key counts. */
typedef struct {ClutterModifierType pressed,latched,locked;} ClutterModifierSet;
extern ClutterEvent *clutter_event_key_new(ClutterEventType,ClutterEventFlags,int64_t,ClutterInputDevice *,ClutterModifierSet,ClutterModifierType,uint32_t,uint32_t,uint32_t,gunichar);
void waystroke_clipboard_x11_replay(GObject *source,guint keyval,guint keycode,guint modifiers,guint pressed,guint latched,guint locked) {
    ClutterModifierSet raw={pressed,latched,locked};guint64 time=g_get_monotonic_time();
    for(guint release=0;release<2;release++) {
        ClutterEvent *event=clutter_event_key_new(release?CLUTTER_KEY_RELEASE:CLUTTER_KEY_PRESS,CLUTTER_EVENT_FLAG_INPUT_METHOD,time+release,CLUTTER_INPUT_DEVICE(source),raw,modifiers,keyval,keycode-8,keycode,clutter_keysym_to_unicode(keyval));
        clutter_event_put(event);clutter_event_free(event);
    }
}
