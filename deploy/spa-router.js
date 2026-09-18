// CloudFront Function (viewer request). Attach to the DEFAULT (*) behaviour only.
//
// WHY THIS EXISTS INSTEAD OF A CUSTOM ERROR RESPONSE
// -------------------------------------------------
// React Router owns the URL, so /accounts/5 is a route in the browser, not a
// file in the bucket. Refreshing that page asks S3 for a key that does not
// exist. The usual fix is a CloudFront custom error response mapping 403 and
// 404 to /index.html with a 200.
//
// That fix is wrong for this distribution. Custom error responses apply to the
// WHOLE distribution, not to one behaviour - so they would also rewrite the
// API's errors. This API uses those exact codes and means them:
//
//     404   an account that is not yours (see AGENTS.md - deliberately not 403,
//           so an attacker cannot use the status to discover which ids exist)
//     403   NotAuthorized
//
// Both would come back as 200 with a page of HTML, and `lib/api.js` would try
// to JSON.parse the app shell. Every permission check in the product would
// appear to succeed. Rewriting the path here instead keeps the fallback on the
// S3 behaviour, where it belongs, and leaves /api/* untouched.
function handler(event) {
  var request = event.request;
  var uri = request.uri;

  // A directory-style path is never a real key.
  if (uri.endsWith('/')) {
    request.uri = '/index.html';
    return request;
  }

  // No dot in the last segment means no file extension, so this is a client
  // side route (/accounts/5, /transactions) rather than an asset
  // (/assets/index-CXVdsTI-.js, /favicon.ico). Vite emits every asset with an
  // extension, so the test holds for everything in dist/.
  var lastSegment = uri.substring(uri.lastIndexOf('/') + 1);
  if (lastSegment.indexOf('.') === -1) {
    request.uri = '/index.html';
  }

  return request;
}
