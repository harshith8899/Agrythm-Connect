import React from 'react';

// A thin track with a bar sliding along it. tone: 'navy' (default) or 'amber'.
export const SliderLoader = ({ tone = 'navy', className = '' }) => (
  <div
    className={`relative h-1 w-full overflow-hidden rounded-full ${tone === 'amber' ? 'bg-amber-100' : 'bg-slate-100'} ${className}`}
    role="progressbar"
    aria-label="Loading"
  >
    <div className={`slider-bar ${tone === 'amber' ? 'bg-amber-500' : 'bg-trust-navy'}`} />
  </div>
);
