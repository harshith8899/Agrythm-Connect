import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Phone } from 'lucide-react';
import { registerConfirmHost } from '../utils/confirm';

// The in-dashboard confirmation: a card over a blurred, dimmed page. Escape or a click outside cancels.
export const ConfirmHost = () => {
  const [request, setRequest] = useState(null); // { options, resolve }
  const confirmRef = useRef(null);
  const [picked, setPicked] = useState('');

  useEffect(() => registerConfirmHost((options) => new Promise((resolve) => {
    const first = (options.choices || []).find((c) => !c.disabledReason);
    setPicked(first ? first.value : '');
    setRequest({ options, resolve });
  })), []);

  const close = useCallback((answer) => {
    setRequest((current) => {
      if (current) current.resolve(answer);
      return null;
    });
  }, []);

  useEffect(() => {
    if (!request) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') close(false);
    };
    window.addEventListener('keydown', onKey);
    confirmRef.current?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [request, close]);

  if (!request) return null;
  const { title, message, confirmLabel = 'Confirm', cancelLabel = 'Cancel', tone = 'default', choices } = request.options;
  const danger = tone === 'danger';
  const answer = choices ? picked || false : true;

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close(false);
      }}
    >
      <div className="w-full max-w-md bg-white rounded-2xl border border-slate-200 shadow-xl p-6 space-y-4">
        <div className="flex items-start gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${danger ? 'bg-amber-50 text-amber-600' : 'bg-slate-100 text-trust-navy'}`}>
            {danger ? <AlertTriangle className="w-5 h-5" /> : <Phone className="w-5 h-5" />}
          </div>
          <div>
            <h3 id="confirm-title" className="text-base font-bold text-slate-900">{title}</h3>
            <p className="text-sm text-slate-600 mt-1 leading-relaxed">{message}</p>
          </div>
        </div>
        {choices && (
          <div className="space-y-2" role="radiogroup">
            {choices.map((c) => {
              const disabled = Boolean(c.disabledReason);
              const on = picked === c.value;
              return (
                <button
                  key={c.value}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  disabled={disabled}
                  onClick={() => setPicked(c.value)}
                  className={`w-full text-left p-3 rounded-xl border transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-60 ${
                    on ? 'border-trust-navy bg-slate-50' : 'border-slate-200 hover:bg-slate-50'
                  }`}
                >
                  <span className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                    <span className={`w-3.5 h-3.5 rounded-full border-2 ${on ? 'border-trust-navy bg-trust-navy' : 'border-slate-300'}`} />
                    {c.label}
                  </span>
                  <span className="block text-xs text-slate-600 mt-1 pl-5.5 leading-relaxed">{disabled ? c.disabledReason : c.description}</span>
                </button>
              );
            })}
          </div>
        )}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={() => close(false)}
            className="px-4 py-2 rounded-xl bg-slate-100 text-slate-700 text-xs font-semibold hover:bg-slate-200 cursor-pointer"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={() => close(answer)}
            disabled={!answer}
            className={`px-4 py-2 rounded-xl text-white text-xs font-semibold cursor-pointer disabled:opacity-50 ${danger ? 'bg-amber-600 hover:bg-amber-700' : 'bg-trust-navy hover:bg-slate-800'}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};
