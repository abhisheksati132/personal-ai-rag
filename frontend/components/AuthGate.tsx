'use client';

import React, { useState } from 'react';
import { login, getApiBase } from '@/lib/api';

interface AuthGateProps {
  onSuccess: () => void;
}

export const AuthGate: React.FC<AuthGateProps> = ({ onSuccess }) => {
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [customApiUrl, setCustomApiUrl] = useState(() => getApiBase());
  const [showSettings, setShowSettings] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim()) {
      setError('Please enter the password');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      if (customApiUrl.trim()) {
        localStorage.setItem('brain_api_url', customApiUrl.trim().replace(/\/+$/, ''));
      }
      await login(password);
      onSuccess();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to authenticate. Please check your credentials.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F6F5F2] flex items-center justify-center p-4 selection:bg-[#E2DFD8]">
      <div className="w-full max-w-md bg-[#FAF9F5] border border-[#E2DFD8] rounded-2xl shadow-xl p-8 sm:p-10 relative overflow-hidden">
        {/* Decorative Archive Header Stamp */}
        <div className="absolute top-0 left-0 right-0 h-1.5 bg-[#3D5A4C]" />

        <div className="flex flex-col items-center text-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-[#EFECE6] border border-[#E2DFD8] flex items-center justify-center text-[#3D5A4C] shadow-inner mb-4">
            <svg
              className="w-7 h-7"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth="1.8"
            >
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
          </div>

          <h1 className="font-serif text-2xl sm:text-3xl text-[#1C1B1A] font-semibold tracking-tight">
            Personal AI Brain
          </h1>
          <p className="font-sans text-xs text-[#8A8578] tracking-widest uppercase mt-1">
            Private Cloud Instance · Restricted
          </p>
        </div>

        {error && (
          <div className="mb-6 bg-red-50/80 border border-red-200/80 rounded-lg p-3 text-red-700 text-xs font-mono flex items-center gap-2 animate-shake">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500 flex-shrink-0" />
            <p className="flex-1">{error}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label
              htmlFor="instance-password"
              className="block font-mono text-xs uppercase tracking-wider text-[#5A554C] mb-2 font-medium"
            >
              Master Password
            </label>
            <div className="relative">
              <input
                id="instance-password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter instance access password"
                disabled={isLoading}
                autoFocus
                className="w-full bg-[#FFFFFF] border border-[#D5D0C7] focus:border-[#3D5A4C] focus:ring-1 focus:ring-[#3D5A4C] rounded-lg px-4 py-3 text-sm text-[#1C1B1A] placeholder-[#A09B90] font-sans transition-all outline-hidden shadow-2xs"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[#8A8578] hover:text-[#1C1B1A] p-1 transition-colors"
                title={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  </svg>
                )}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-[#1C1B1A] hover:bg-[#2C2B2A] active:bg-[#000000] text-[#FAF9F5] font-sans font-medium text-sm py-3 px-4 rounded-lg transition-all duration-150 flex items-center justify-center gap-2 shadow-xs cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <>
                <span className="w-4 h-4 border-2 border-[#FAF9F5] border-t-transparent rounded-full animate-spin" />
                <span>Verifying Access...</span>
              </>
            ) : (
              <span>Unlock Brain</span>
            )}
          </button>
        </form>

        <div className="mt-8 pt-6 border-t border-[#EFECE6] text-center">
          <button
            type="button"
            onClick={() => setShowSettings(!showSettings)}
            className="font-mono text-xs text-[#8A8578] hover:text-[#1C1B1A] transition-colors"
          >
            {showSettings ? '▾ Hide Backend Configuration' : '▸ Backend Configuration'}
          </button>

          {showSettings && (
            <div className="mt-4 text-left p-3 bg-[#F0EEEA] rounded-lg border border-[#E2DFD8]">
              <label
                htmlFor="backend-url"
                className="block font-mono text-[10px] uppercase text-[#6B655C] mb-1"
              >
                API Target URL
              </label>
              <input
                id="backend-url"
                type="text"
                value={customApiUrl}
                onChange={(e) => setCustomApiUrl(e.target.value)}
                placeholder="https://your-api.onrender.com"
                className="w-full bg-white border border-[#D5D0C7] rounded px-2.5 py-1.5 font-mono text-xs text-[#1C1B1A]"
              />
              <p className="font-sans text-[11px] text-[#8A8578] mt-1.5">
                Target FastAPI backend serving the private brain instance.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
