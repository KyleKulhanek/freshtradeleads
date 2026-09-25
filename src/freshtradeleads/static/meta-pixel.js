(function () {
  "use strict";

  var pixelId = document.documentElement.dataset.metaPixelId;
  if (!pixelId || !/^\d+$/.test(pixelId)) return;

  if (!window.fbq) {
    var fbq = function () { fbq.callMethod ? fbq.callMethod.apply(fbq, arguments) : fbq.queue.push(arguments); };
    fbq.push = fbq;
    fbq.loaded = true;
    fbq.version = "2.0";
    fbq.queue = [];
    window.fbq = fbq;
    window._fbq = fbq;
    var script = document.createElement("script");
    script.async = true;
    script.src = "https://connect.facebook.net/en_US/fbevents.js";
    document.head.appendChild(script);
  }

  window.fbq("init", pixelId);
  window.fbq("track", "PageView");

  document.querySelectorAll("form[data-meta-checkout]").forEach(function (form) {
    form.addEventListener("submit", function () {
      window.fbq("track", "InitiateCheckout", {
        content_ids: [form.dataset.metaSku],
        content_name: form.dataset.metaName,
        content_type: "product",
        currency: "USD",
        num_items: Number(form.dataset.metaLeads),
        value: Number(form.dataset.metaValue)
      });
    }, { once: true });
  });

  var purchase = document.querySelector("[data-meta-purchase]");
  if (purchase) {
    window.fbq("track", "Purchase", {
      content_ids: [purchase.dataset.metaSku],
      content_type: "product",
      currency: "USD",
      num_items: Number(purchase.dataset.metaLeads),
      value: Number(purchase.dataset.metaValue)
    }, { eventID: "purchase_" + purchase.dataset.metaOrder });
  }
})();
