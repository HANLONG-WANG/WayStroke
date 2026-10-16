use gtk::glib::translate::ToGlibPtr;
use std::ffi::c_void;
use webkit2gtk::{SettingsExt, WebViewExt};

// WebKitGTK's feature API (2.46+) is not yet exposed by webkit2gtk-rs 2.0.
#[link(name = "webkit2gtk-4.1")]
unsafe extern "C" {
    fn webkit_settings_get_all_features() -> *mut c_void;
    fn webkit_feature_list_find(list: *mut c_void, identifier: *const std::ffi::c_char) -> *mut c_void;
    fn webkit_settings_set_feature_enabled(settings: *mut webkit2gtk::ffi::WebKitSettings, feature: *mut c_void, enabled: i32);
    fn webkit_feature_list_unref(list: *mut c_void);
}

pub fn configure(webview: &webkit2gtk::WebView) {
    let settings = WebViewExt::settings(webview).expect("webview settings");
    // Let animations and requestAnimationFrame follow the current monitor.
    // Do not force a fixed FPS: Wayland/WebKit tracks monitor changes itself.
    unsafe {
        let features = webkit_settings_get_all_features();
        let feature = webkit_feature_list_find(features, c"PreferPageRenderingUpdatesNear60FPS".as_ptr());
        if !feature.is_null() {
            webkit_settings_set_feature_enabled(settings.to_glib_none().0, feature, 0);
        } else {
            eprintln!("WayStroke: WebKitGTK does not expose the near-60fps rendering preference");
        }
        webkit_feature_list_unref(features);
    }
    settings.set_enable_smooth_scrolling(true);
}
