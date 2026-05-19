import React from 'react';

interface LanguageSwitcherProps {
  uiLang: string;
  onToggle: () => void;
}

export default function LanguageSwitcher({ uiLang, onToggle }: LanguageSwitcherProps) {
  const isJa = uiLang === 'ja';
  return (
    <button
      className={`lang-switcher ${isJa ? 'lang-switcher--ja' : 'lang-switcher--en'}`}
      onClick={onToggle}
      id="lang-switcher-btn"
      title={isJa ? 'Switch to English' : '日本語に切り替え'}
    >
      <span className="lang-flag">{isJa ? '🇯🇵' : '🇬🇧'}</span>
      <span className="lang-label">{isJa ? 'JP' : 'EN'}</span>
    </button>
  );
}
