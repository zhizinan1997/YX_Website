function setIframeHeightAfterLoad(id) {
  try {
      var iframe = document.getElementById(id);
      if (iframe.attachEvent) {
          iframe.attachEvent("onload", function () {
              iframe.height = iframe.contentWindow.document.documentElement.scrollHeight;
          });
          return;

      } else {
          iframe.onload = function () {
              iframe.height = iframe.contentDocument.body.scrollHeight;
          };
          return;
      }
  } catch (e) {
      throw new Error('setIframeHeightAfterLoad Error');
  }
};

function setIframeHeight(id) {
  try {
      var iframe = document.getElementById(id);
      if (iframe.attachEvent) {
          iframe.height = iframe.contentWindow.document.documentElement.scrollHeight;
          return;

      } else {
          iframe.height = iframe.contentDocument.body.scrollHeight;
          return;
      }
  } catch (e) {
      throw new Error('setIframeHeight Error');
  }
};

function setParentIframeHeight(id) {
  try {
      var parentIframe = parent.document.getElementById(id);
      if (window.attachEvent) {
          window.attachEvent("onload", function () {
              parentIframe.height = document.documentElement.scrollHeight;
          });
          return;
      } else {
          window.onload = function () {
              parentIframe.height = document.body.scrollHeight;
          };
          return;
      }
  } catch (e) {
      throw new Error('setParentIframeHeight Error');
  }
};

function thisIframeHeightAuto() {
  setIframeHeight("jobs");
};

$(function () {
  window.setInterval("thisIframeHeightAuto()", 200);
});