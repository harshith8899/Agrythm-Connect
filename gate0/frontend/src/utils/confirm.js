// A confirmation shown inside the dashboard (with a blurred background) instead of the browser's own dialog.
// <ConfirmHost /> (rendered once in App) registers itself here; confirmDialog() resolves true or false.
let host = null;

export const registerConfirmHost = (fn) => {
  host = fn;
  return () => {
    if (host === fn) host = null;
  };
};

/** options: { title, message, confirmLabel, cancelLabel, tone: 'danger' | 'default' } */
export const confirmDialog = (options) => (host ? host(options) : Promise.resolve(window.confirm(options.message)));
