// Main frontend behaviors (NProgress, global form/button handlers, maintenance/panic helpers, flash auto-dismiss, CSRF injection)
(function () {
  document.addEventListener('DOMContentLoaded', function () {
    // NProgress Configuration
    if (window.NProgress) NProgress.configure({ showSpinner: false });

    // Helper to announce long operations for screen readers
    window.announceProgress = (msg) => {
      const el = document.getElementById('nprogress-announce');
      if (!el) return;
      el.textContent = msg || '';
      setTimeout(() => { el.textContent = ''; }, 2000);
    };

    // Page Transition Loading
    window.addEventListener('beforeunload', function () {
      if (window.NProgress) NProgress.start();
    });

    // Also trigger on link clicks for immediate feedback
    document.addEventListener('click', (e) => {
      const link = e.target.closest('a');
      if (link &&
        !link.target &&
        !link.hasAttribute('download') &&
        link.href &&
        link.href.startsWith(window.location.origin) &&
        !link.href.includes('#') &&
        !e.ctrlKey && !e.metaKey && !e.shiftKey && !e.altKey
      ) {
        if (window.NProgress) NProgress.start();
      }
    });

    window.addEventListener('load', function () {
      if (window.NProgress) NProgress.done();
    });

    // Global Button Loading
    document.addEventListener('submit', function (e) {
      const form = e.target;
      const submitBtn = form.querySelector('[type="submit"], button:not([type="button"]):not([type="reset"])');

      if (submitBtn && !submitBtn.classList.contains('no-loading')) {
        if (submitBtn.disabled) {
          e.preventDefault();
          return;
        }

        submitBtn.dataset.originalContent = submitBtn.innerHTML;
        const loadingText = submitBtn.dataset.loadingText || 'Loading...';
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>${loadingText}`;
      }
    });

    // Restore button state (bfcache)
    window.addEventListener('pageshow', function (event) {
      if (event.persisted) {
        const submitBtns = document.querySelectorAll('[type="submit"][disabled], button[disabled]');
        submitBtns.forEach(btn => {
          if (btn.dataset.originalContent) {
            btn.innerHTML = btn.dataset.originalContent;
            btn.disabled = false;
          }
        });
        if (window.NProgress) NProgress.done();
      }
    });

    // Maintenance banner persistence (localStorage)
    try {
      const maintBar = document.querySelector('.maintenance-bar');
      if (maintBar) {
        const textEl = maintBar.querySelector('.maintenance-text');
        const msg = textEl ? textEl.textContent.trim() : '';
        const key = 'maintenance_dismissed:' + btoa(msg);
        if (localStorage.getItem(key)) {
          maintBar.style.display = 'none';
        }
        maintBar.querySelectorAll('.maintenance-close').forEach(btn => {
          btn.addEventListener('click', function () {
            try { localStorage.setItem(key, '1'); } catch(e) {}
            const bar = this.closest('.maintenance-bar');
            if (bar) bar.style.display = 'none';
          });
        });
      }
    } catch (e) {
      // ignore localStorage errors
    }

    // Panic modal behavior: show modal and overlay; admin can bypass
    try {
      const panicModal = document.getElementById('panicModal');
      const panicOverlay = document.getElementById('panicOverlay');
      if (panicModal && panicOverlay) {
        panicOverlay.style.display = 'block';
        panicModal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
        panicModal.querySelectorAll('button, a').forEach(el => el.setAttribute('tabindex', '0'));

        const isAdmin = panicModal.getAttribute('data-admin') === '1';
        if (isAdmin) {
          const cont = document.getElementById('panicContinue');
          if (cont) cont.addEventListener('click', function () {
            const tokenMeta = document.querySelector('meta[name="csrf-token"]');
            const token = tokenMeta ? tokenMeta.getAttribute('content') : null;
            fetch('/panic/bypass', {
              method: 'POST',
              headers: token ? { 'X-CSRF-Token': token, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' },
              body: JSON.stringify({})
            }).then(r => {
              panicOverlay.style.display = 'none';
              panicModal.style.display = 'none';
              document.body.style.overflow = '';
            }).catch(() => {
              panicOverlay.style.display = 'none';
              panicModal.style.display = 'none';
              document.body.style.overflow = '';
            });
          });
        }
      }
    } catch (e) {
      // ignore
    }

    // Auto-dismiss flash alerts after 5 seconds
    const alerts = document.querySelectorAll('.flash-container .alert');
    alerts.forEach(alert => {
      setTimeout(() => {
        alert.style.opacity = '0';
        alert.style.transform = 'translateY(-10px)';
        setTimeout(() => alert.remove(), 300);
      }, 5000);
    });

    // Policies admin: edit button + search filter
    // Edit button navigation
    document.querySelectorAll('.btn-edit').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var href = this.dataset && this.dataset.href;
        if (href) window.location = href;
      });
    });

    // Client-side search for policies table
    var policySearch = document.getElementById('policySearch');
    if (policySearch) {
      policySearch.addEventListener('input', function() {
        var q = this.value.trim().toLowerCase();
        document.querySelectorAll('#policiesTable tbody tr').forEach(function(row) {
          var k = row.getAttribute('data-key') || '';
          var v = row.getAttribute('data-value') || '';
          if (!q || k.indexOf(q) !== -1 || v.indexOf(q) !== -1) {
            row.style.display = '';
          } else {
            row.style.display = 'none';
          }
        });
      });
    }

    // View value modal + copy-to-clipboard for policies
    var viewModalEl = document.getElementById('viewValueModal');
    if (viewModalEl) {
      // attach click handlers to view buttons
      document.querySelectorAll('.view-value').forEach(function(btn) {
        btn.addEventListener('click', function() {
          var key = this.dataset && this.dataset.key || '';
          var val = this.dataset && this.dataset.value || '';
          var titleEl = viewModalEl.querySelector('#viewValueModalLabel');
          var contentEl = viewModalEl.querySelector('#viewValueContent');

          // Decode HTML entities (attribute may contain escaped JSON) and detect JSON
          function decodeHtmlEntities(s) {
            try {
              var txt = document.createElement('textarea');
              txt.innerHTML = s;
              return txt.value;
            } catch (e) { return s; }
          }

          var decodedVal = decodeHtmlEntities(val);

          // Lenient JSON parser that can handle Python-style literals, single-quoted strings,
          // unquoted keys and trailing commas. Returns parsed object or null.
          function lenientJSONParse(s) {
            try {
              if (!s || typeof s !== 'string') return null;
              var t = s.trim();
              // If wrapped in single quotes, strip them
              if (t.length >= 2 && t[0] === "'" && t[t.length-1] === "'") {
                t = t.slice(1, -1).trim();
              }

              // Try quick JSON first
              try { return JSON.parse(t); } catch (e) {}

              // If it contains an obvious object/array, try to normalize
              var hasBraces = t.indexOf('{') !== -1 || t.indexOf('[') !== -1;
              if (!hasBraces) return null;

              var norm = t;

              // If value contains HTML-escaped sequences like &#39;, assume decodeHtmlEntities handled it
              // Wrap unquoted keys: {foo: -> "foo":
              norm = norm.replace(/([,{]\s*)([a-zA-Z_][a-zA-Z0-9_\-]*)(\s*:)/g, '$1"$2"$3');

              // Replace single-quoted strings with proper JSON-quoted strings safely
              norm = norm.replace(/'([^'\\]*(?:\\.[^'\\]*)*)'/g, function(m, p1) {
                // JSON.stringify handles escaping
                return JSON.stringify(p1);
              });

              // Convert Python booleans/None to JSON
              norm = norm.replace(/\bTrue\b/g, 'true').replace(/\bFalse\b/g,'false').replace(/\bNone\b/g,'null');

              // Remove trailing commas before } or ]
              norm = norm.replace(/,\s*([}\]])/g, '$1');

              // Attempt parse
              return JSON.parse(norm);
            } catch (e) {
              return null;
            }
          }

          // Detect JSON and pretty-print if possible, with sensitive masking
          var pretty = decodedVal;
          var isJson = false;

          // Sanitizer: mask sensitive fields (partial mask) recursively
          function maskPartial(s, keep) {
            s = String(s || '');
            keep = typeof keep === 'number' ? keep : 4;
            if (s.length <= keep) return '*'.repeat(s.length);
            return '*'.repeat(Math.max(0, s.length - keep)) + s.slice(-keep);
          }
          function sanitizeObject(obj) {
            var sensitive = ['account_number','cin','card_number','ssn','token'];
            if (obj === null) return null;
            if (Array.isArray(obj)) return obj.map(sanitizeObject);
            if (typeof obj === 'object') {
              var out = {};
              Object.keys(obj).forEach(function(k){
                var v = obj[k];
                try {
                  // If the value is an object/array, recurse
                  if (v && typeof v === 'object') {
                    out[k] = sanitizeObject(v);

                  // If the value is a string, attempt to parse it as JSON (handles nested arrays stored as strings)
                  } else if (typeof v === 'string') {
                    var s = v.trim();
                    var parsedInner = lenientJSONParse(s);
                    if (parsedInner !== null) {
                      out[k] = sanitizeObject(parsedInner);
                    } else if (sensitive.indexOf(k) !== -1) {
                      out[k] = maskPartial(v, 4);
                    } else {
                      out[k] = v;
                    }

                  } else if (sensitive.indexOf(k) !== -1) {
                    out[k] = maskPartial(v, 4);
                  } else {
                    out[k] = v;
                  }
                } catch (e) {
                  out[k] = '[REDACTED]';
                }
              });
              return out;
            }
            return obj;
          }

          // 1) Try JSON.parse
          try {
            var parsed = JSON.parse(decodedVal);
            var sanitized = sanitizeObject(parsed);
            pretty = JSON.stringify(sanitized, null, 2);
            isJson = true;
          } catch (e) {
            // 2) Try lenient parser which handles Python-like and other variants
            var parsed2 = lenientJSONParse(decodedVal);
            if (parsed2 !== null) {
              var sanitized2 = sanitizeObject(parsed2);
              pretty = JSON.stringify(sanitized2, null, 2);
              isJson = true;
            } else {
              // keep decoded string
              pretty = decodedVal;
              isJson = false;
            }
          }

          if (titleEl) titleEl.textContent = key ? ('Value — ' + key + (isJson ? ' (JSON, preview)' : '')) : 'Value';
          if (contentEl) contentEl.textContent = pretty;

          if (window.bootstrap && window.bootstrap.Modal) {
            var inst = bootstrap.Modal.getOrCreateInstance(viewModalEl);
            inst.show();
          } else {
            // Fallback: simple show/hide without Bootstrap JS
            var showModal = function() {
              viewModalEl.classList.add('show');
              viewModalEl.setAttribute('aria-hidden', 'false');
              document.body.style.overflow = 'hidden';

              // attach close handlers
              viewModalEl.querySelectorAll('[data-bs-dismiss]').forEach(function(btn){
                btn.addEventListener('click', hideModal);
              });

              // clicking on backdrop closes
              viewModalEl.addEventListener('click', function backdropClose(e) {
                if (e.target === viewModalEl) hideModal();
              });
            };

            var hideModal = function() {
              viewModalEl.classList.remove('show');
              viewModalEl.setAttribute('aria-hidden', 'true');
              document.body.style.overflow = '';
            };

            // show it now
            showModal();
          }
        });
      });

      var copyBtn = document.getElementById('copyValueBtn');
      if (copyBtn) {
        // Fallback copy method for browsers without navigator.clipboard
        function fallbackCopyTextToClipboard(text) {
          try {
            var textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.setAttribute('readonly', '');
            textarea.style.position = 'absolute';
            textarea.style.left = '-9999px';
            document.body.appendChild(textarea);

            var selected = null;
            if (document.getSelection && document.getSelection().rangeCount > 0) {
              selected = document.getSelection().getRangeAt(0);
            }

            textarea.select();
            textarea.setSelectionRange(0, textarea.value.length);
            var successful = document.execCommand('copy');

            document.body.removeChild(textarea);
            if (selected) {
              document.getSelection().removeAllRanges();
              document.getSelection().addRange(selected);
            }
            return successful;
          } catch (e) {
            try { if (textarea && textarea.parentNode) textarea.parentNode.removeChild(textarea); } catch (e) {}
            return false;
          }
        }

        copyBtn.addEventListener('click', function() {
          var contentEl = document.getElementById('viewValueContent');
          if (!contentEl) return;
          var text = contentEl.textContent || '';

          var onSuccess = function() {
            var orig = copyBtn.innerHTML;
            copyBtn.innerHTML = 'Copied ✓';
            copyBtn.disabled = true;
            setTimeout(function() {
              copyBtn.innerHTML = orig;
              copyBtn.disabled = false;
            }, 1500);
          };

          var onError = function() {
            var orig = copyBtn.innerHTML;
            copyBtn.innerHTML = 'Error';
            setTimeout(function() { copyBtn.innerHTML = orig; }, 1500);
          };

          if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
            navigator.clipboard.writeText(text).then(onSuccess).catch(function() {
              var ok = fallbackCopyTextToClipboard(text);
              if (ok) onSuccess(); else onError();
            });
          } else {
            var ok = fallbackCopyTextToClipboard(text);
            if (ok) onSuccess(); else onError();
          }
        });
      }
    }

  }); // DOMContentLoaded end

  // Inject CSRF token into all POST forms if missing (runs immediately)
  (function(){
    const tokenMeta = document.querySelector('meta[name="csrf-token"]');
    if (!tokenMeta) return;
    const token = tokenMeta.getAttribute('content');
    if (!token) return;
    document.querySelectorAll('form[method="post"]').forEach(function(form){
      if (!form.querySelector('input[name="csrf_token"]')){
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'csrf_token';
        input.value = token;
        form.appendChild(input);
      }
    });
  })();
})();
