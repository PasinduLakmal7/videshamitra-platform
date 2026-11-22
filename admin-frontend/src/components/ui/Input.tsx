import React from 'react';

type InputProps = React.InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  error?: string | null;
  hint?: string;
};

export const Input: React.FC<InputProps> = ({ label, error, hint, id, className = '', ...rest }) => {
  const inputId = id ?? rest.name;
  return (
    <label className={`field ${className}`} htmlFor={inputId}>
      {label && <span className="field-label">{label}</span>}
      <input id={inputId} className={`input ${error ? 'input-error' : ''}`} {...rest} />
      {hint && !error && <span className="field-hint">{hint}</span>}
      {error && <span className="field-error">{error}</span>}
    </label>
  );
};

type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label?: string;
  error?: string | null;
};

export const Textarea: React.FC<TextareaProps> = ({ label, error, id, className = '', ...rest }) => {
  const inputId = id ?? rest.name;
  return (
    <label className={`field ${className}`} htmlFor={inputId}>
      {label && <span className="field-label">{label}</span>}
      <textarea id={inputId} className={`input textarea ${error ? 'input-error' : ''}`} {...rest} />
      {error && <span className="field-error">{error}</span>}
    </label>
  );
};

type SelectProps = React.SelectHTMLAttributes<HTMLSelectElement> & {
  label?: string;
  options: { value: string; label: string }[];
};

export const Select: React.FC<SelectProps> = ({ label, options, id, className = '', ...rest }) => {
  const inputId = id ?? rest.name;
  return (
    <label className={`field ${className}`} htmlFor={inputId}>
      {label && <span className="field-label">{label}</span>}
      <select id={inputId} className="input" {...rest}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
};
