// ignore_for_file: avoid_web_libraries_in_flutter
import 'dart:ui_web' as ui_web;
import 'dart:js_interop';
import 'package:web/web.dart' as web;

/// Registers an iframe platform view for Flutter Web.
void registerDocIframe(String viewId, String fullHtml) {
  ui_web.platformViewRegistry.registerViewFactory(viewId, (int id) {
    final iframe = web.document.createElement('iframe') as web.HTMLIFrameElement;
    iframe.style
      ..width = '100%'
      ..height = '100%'
      ..border = 'none'
      ..backgroundColor = '#ffffff';
    iframe.setAttribute('sandbox', 'allow-same-origin allow-scripts');
    iframe.setAttribute('srcdoc', fullHtml);
    return iframe;
  });
}

/// Find the contenteditable iframe document
web.Document? _getIframeDoc() {
  try {
    final iframes = web.document.querySelectorAll('iframe');
    for (int i = iframes.length - 1; i >= 0; i--) {
      final iframe = iframes.item(i) as web.HTMLIFrameElement?;
      if (iframe != null && iframe.contentDocument != null) {
        return iframe.contentDocument!;
      }
    }
  } catch (_) {}
  return null;
}

/// Extracts edited HTML from the iframe body.
String? getIframeBodyHtml() {
  final doc = _getIframeDoc();
  if (doc?.body != null) {
    return (doc!.body!.innerHTML as JSString).toDart;
  }
  return null;
}

/// Execute a formatting command inside the iframe (like document.execCommand).
void iframeExecCommand(String command, [String? value]) {
  final doc = _getIframeDoc();
  if (doc != null) {
    doc.execCommand(command, false, value ?? '');
  }
}

/// Trigger a file download in the browser.
void downloadFile(String url, String filename) {
  final a = web.document.createElement('a') as web.HTMLAnchorElement;
  a.href = url;
  a.setAttribute('download', filename);
  a.style.display = 'none';
  web.document.body!.appendChild(a);
  a.click();
  a.remove();
}
