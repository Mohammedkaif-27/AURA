import React, { useEffect, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';

export default function ConfirmModal({ isOpen, onClose, onConfirm, title, message, confirmText = "Confirm", isDestructive = true }) {
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setShow(true);
    } else {
      const timer = setTimeout(() => setShow(false), 300);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  if (!isOpen && !show) return null;

  return (
    <div className={`fixed inset-0 z-[100] flex items-end sm:items-center justify-center p-0 sm:p-4 transition-all duration-300 ${isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}>
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/40 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />
      
      {/* Modal — bottom sheet on mobile, centered on desktop */}
      <div 
        className={`relative w-full sm:max-w-md overflow-hidden bg-white shadow-2xl transition-all duration-300
                    rounded-t-3xl sm:rounded-2xl
                    ${isOpen ? 'translate-y-0 scale-100' : 'translate-y-full sm:translate-y-0 sm:scale-95'}`}
      >
        {/* Drag handle (mobile only) */}
        <div className="sm:hidden flex justify-center pt-3 pb-1">
          <div className="w-10 h-1 rounded-full bg-gray-300" />
        </div>

        <div className="p-5 sm:p-6">
          <div className="flex items-start gap-4">
            <div className={`flex h-10 w-10 sm:h-11 sm:w-11 flex-shrink-0 items-center justify-center rounded-xl ${isDestructive ? 'bg-red-100 text-red-600' : 'bg-blue-100 text-blue-600'}`}>
              <AlertTriangle size={20} />
            </div>
            
            <div className="flex-1 pt-0.5">
              <h3 className="text-base sm:text-lg font-semibold text-gray-900">{title}</h3>
              <p className="mt-1.5 text-sm text-gray-500 leading-relaxed">{message}</p>
            </div>
            
            <button 
              onClick={onClose}
              className="ml-auto inline-flex h-9 w-9 items-center justify-center rounded-xl text-gray-400 
                         hover:bg-gray-100 hover:text-gray-500 transition-colors"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="px-5 sm:px-6 pb-5 sm:pb-6 pt-2 flex flex-col-reverse sm:flex-row items-stretch sm:items-center sm:justify-end gap-2 sm:gap-3">
          <button
            type="button"
            className="rounded-xl px-4 py-3 sm:py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-100 
                       transition-colors focus:outline-none border border-border press-scale"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="button"
            className={`rounded-xl px-4 py-3 sm:py-2.5 text-sm font-medium text-white transition-all 
                       focus:outline-none focus:ring-2 focus:ring-offset-2 press-scale ${
              isDestructive 
                ? 'bg-red-600 hover:bg-red-700 focus:ring-red-500' 
                : 'bg-blue-600 hover:bg-blue-700 focus:ring-blue-500'
            }`}
            onClick={() => {
              onConfirm();
              onClose();
            }}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
