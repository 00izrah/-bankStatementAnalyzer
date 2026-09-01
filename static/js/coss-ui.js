/**
 * coss UI JavaScript Interaction Engine
 * Handles Dialog, Sheet / Drawer, Toast, Tabs / Segmented Control, and Keyboard Shortcuts
 */

(function () {
  'use strict';

  // ==========================================
  // Toast Manager
  // ==========================================
  const CossToast = {
    container: null,

    init() {
      if (!this.container) {
        this.container = document.getElementById('coss-toast-container');
        if (!this.container) {
          this.container = document.createElement('div');
          this.container.id = 'coss-toast-container';
          document.body.appendChild(this.container);
        }
      }
    },

    show({ title, description, variant = 'default', duration = 4000 }) {
      this.init();
      const toast = document.createElement('div');
      toast.className = `coss-toast border ${this.getVariantStyles(variant)}`;

      const iconSvg = this.getVariantIcon(variant);

      toast.innerHTML = `
        <div class="shrink-0 mt-0.5">${iconSvg}</div>
        <div class="flex-1">
          ${title ? `<p class="text-xs font-semibold text-gray-900">${escapeHtml(title)}</p>` : ''}
          ${description ? `<p class="text-xs text-gray-600 mt-0.5 leading-relaxed">${escapeHtml(description)}</p>` : ''}
        </div>
        <button type="button" class="shrink-0 text-gray-400 hover:text-gray-600 p-0.5 rounded focus:outline-none" aria-label="Dismiss toast">
          <svg class="size-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
          </svg>
        </button>
      `;

      const closeBtn = toast.querySelector('button');
      closeBtn.addEventListener('click', () => {
        this.dismiss(toast);
      });

      this.container.appendChild(toast);

      if (duration > 0) {
        setTimeout(() => {
          this.dismiss(toast);
        }, duration);
      }
    },

    dismiss(toast) {
      if (!toast) return;
      toast.style.opacity = '0';
      toast.style.transform = 'scale(0.95)';
      toast.style.transition = 'all 150ms ease';
      setTimeout(() => {
        toast.remove();
      }, 150);
    },

    getVariantStyles(variant) {
      switch (variant) {
        case 'success':
          return 'bg-card border-success/30 text-card-foreground shadow-coss-sm';
        case 'destructive':
        case 'error':
          return 'bg-card border-destructive/30 text-card-foreground shadow-coss-sm';
        case 'warning':
          return 'bg-card border-warning/30 text-card-foreground shadow-coss-sm';
        default:
          return 'bg-card border-border text-card-foreground shadow-coss-sm';
      }
    },

    getVariantIcon(variant) {
      switch (variant) {
        case 'success':
          return '<i class="hgi-stroke hgi-checkmark-circle-02 text-base text-success"></i>';
        case 'destructive':
        case 'error':
          return '<i class="hgi-stroke hgi-cancel-circle text-base text-destructive"></i>';
        case 'warning':
          return '<i class="hgi-stroke hgi-alert-circle text-base text-warning"></i>';
        default:
          return '<i class="hgi-stroke hgi-information-circle text-base text-primary"></i>';
      }
    }
  };

  // ==========================================
  // Dialog / Modal Controller
  // ==========================================
  const CossDialog = {
    open(dialogId) {
      const dialog = document.getElementById(dialogId);
      if (!dialog) return;
      dialog.classList.remove('hidden');
      setTimeout(() => {
        dialog.classList.add('open');
      }, 10);
      document.body.classList.add('overflow-hidden');
    },

    close(dialogId) {
      const dialog = document.getElementById(dialogId);
      if (!dialog) return;
      dialog.classList.remove('open');
      setTimeout(() => {
        dialog.classList.add('hidden');
        document.body.classList.remove('overflow-hidden');
      }, 200);
    }
  };

  // ==========================================
  // Sheet / Drawer Controller
  // ==========================================
  const CossSheet = {
    toggle(sheetId, backdropId) {
      const sheet = document.getElementById(sheetId);
      const backdrop = backdropId ? document.getElementById(backdropId) : null;
      if (!sheet) return;

      const isOpen = sheet.classList.contains('open') || !sheet.classList.contains('translate-x-full');
      if (isOpen) {
        this.close(sheetId, backdropId);
      } else {
        this.open(sheetId, backdropId);
      }
    },

    open(sheetId, backdropId) {
      const sheet = document.getElementById(sheetId);
      const backdrop = backdropId ? document.getElementById(backdropId) : null;
      if (!sheet) return;

      sheet.classList.add('open');
      sheet.classList.remove('translate-x-full');
      if (backdrop) {
        backdrop.classList.remove('hidden');
      }
      document.body.classList.add('overflow-hidden');
    },

    close(sheetId, backdropId) {
      const sheet = document.getElementById(sheetId);
      const backdrop = backdropId ? document.getElementById(backdropId) : null;
      if (!sheet) return;

      sheet.classList.remove('open');
      sheet.classList.add('translate-x-full');
      if (backdrop) {
        backdrop.classList.add('hidden');
      }
      document.body.classList.remove('overflow-hidden');
    }
  };

  // ==========================================
  // Tabs & Segmented Controls
  // ==========================================
  const CossTabs = {
    init() {
      document.querySelectorAll('[data-coss-tabs]').forEach(tabsContainer => {
        const triggers = tabsContainer.querySelectorAll('[data-coss-tab-trigger]');
        triggers.forEach(trigger => {
          trigger.addEventListener('click', e => {
            const targetId = trigger.getAttribute('data-coss-tab-target');
            if (!targetId) return;

            // Deactivate all sibling triggers
            triggers.forEach(t => {
              t.classList.remove('active');
              t.setAttribute('aria-selected', 'false');
            });

            // Activate current trigger
            trigger.classList.add('active');
            trigger.setAttribute('aria-selected', 'true');

            // Toggle panels
            const scope = tabsContainer.getAttribute('data-coss-tabs-scope') || '';
            const parentScope = scope ? document.querySelector(scope) : document;
            if (parentScope) {
              parentScope.querySelectorAll('[data-coss-tab-panel]').forEach(panel => {
                panel.classList.add('hidden');
              });
              const targetPanel = parentScope.querySelector(`#${targetId}`);
              if (targetPanel) {
                targetPanel.classList.remove('hidden');
              }
            }
          });
        });
      });
    }
  };

  // Utility: HTML Sanitizer
  function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // Global Keybindings Listener (Escape closes open sheets/dialogs)
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      // Close open dialogs
      document.querySelectorAll('.coss-dialog-popup.open').forEach(dialog => {
        CossDialog.close(dialog.id);
      });
      // Close open sheets
      document.querySelectorAll('.coss-sheet-popup.open').forEach(sheet => {
        CossSheet.close(sheet.id, sheet.getAttribute('data-backdrop-id'));
      });
    }
  });

  // Auto-init on DOMContentLoaded
  document.addEventListener('DOMContentLoaded', () => {
    CossToast.init();
    CossTabs.init();
  });

  // Export to global window namespace
  window.CossToast = CossToast;
  window.toastManager = CossToast; // Alias compatible with coss toastManager
  window.CossDialog = CossDialog;
  window.CossSheet = CossSheet;
  window.CossTabs = CossTabs;
})();
