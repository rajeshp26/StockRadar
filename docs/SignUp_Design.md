# Best-in-Class Signup + Two-Factor Authentication

Here's the complete **multi-step signup flow with 2FA** — every step is beautifully designed, validated, and animated.

---

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Create Account — Nexus</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    :root {
      --bg: #060912;
      --surface: rgba(14, 19, 38, 0.7);
      --surface-2: rgba(20, 28, 56, 0.5);
      --surface-3: rgba(255,255,255,0.03);
      --border: rgba(255,255,255,0.07);
      --border-2: rgba(255,255,255,0.12);
      --text: #f1f5f9;
      --text-muted: #64748b;
      --text-subtle: #475569;
      --accent: #6366f1;
      --accent-light: #818cf8;
      --accent-glow: rgba(99,102,241,0.3);
      --accent-2: #06b6d4;
      --green: #22c55e;
      --green-bg: rgba(34,197,94,0.1);
      --green-border: rgba(34,197,94,0.25);
      --red: #ef4444;
      --red-bg: rgba(239,68,68,0.1);
      --red-border: rgba(239,68,68,0.25);
      --yellow: #f59e0b;
      --yellow-bg: rgba(245,158,11,0.1);
      --orange: #fb923c;
      --gradient-1: linear-gradient(135deg, #6366f1, #8b5cf6, #06b6d4);
      --gradient-2: linear-gradient(135deg, #1e293b, #0f172a);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      overflow-x: hidden;
    }

    /* Animated Background */
    .bg-canvas {
      position: fixed;
      inset: 0;
      z-index: 0;
      overflow: hidden;
    }

    .bg-orb {
      position: absolute;
      border-radius: 50%;
      filter: blur(120px);
      animation: float 25s ease-in-out infinite;
    }

    .bg-orb-1 {
      width: 700px; height: 700px;
      background: radial-gradient(circle, rgba(99,102,241,0.35) 0%, transparent 70%);
      top: -25%; left: -15%;
      animation-delay: 0s;
    }

    .bg-orb-2 {
      width: 600px; height: 600px;
      background: radial-gradient(circle, rgba(6,182,212,0.3) 0%, transparent 70%);
      bottom: -20%; right: -10%;
      animation-delay: -8s;
    }

    .bg-orb-3 {
      width: 450px; height: 450px;
      background: radial-gradient(circle, rgba(139,92,246,0.2) 0%, transparent 70%);
      top: 40%; left: 35%;
      animation-delay: -16s;
    }

    @keyframes float {
      0%, 100% { transform: translate(0,0) scale(1); }
      25% { transform: translate(40px,-50px) scale(1.05); }
      50% { transform: translate(-30px,30px) scale(0.95); }
      75% { transform: translate(50px,40px) scale(1.03); }
    }

    .bg-grid {
      position: fixed;
      inset: 0;
      z-index: 1;
      background-image:
        linear-gradient(rgba(255,255,255,0.015) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.015) 1px, transparent 1px);
      background-size: 70px 70px;
      pointer-events: none;
    }

    /* Layout */
    .split {
      display: flex;
      width: 100%;
      min-height: 100vh;
      position: relative;
      z-index: 2;
    }

    /* Left Panel */
    .left-panel {
      flex: 1.1;
      display: flex;
      flex-direction: column;
      justify-content: center;
      padding: 60px;
      position: relative;
    }

    @media (max-width: 900px) { .left-panel { display: none; } }

    .brand-logo {
      position: absolute;
      top: 40px;
      left: 60px;
      display: flex;
      align-items: center;
      gap: 12px;
      text-decoration: none;
    }

    .logo-icon {
      width: 42px; height: 42px;
      background: var(--gradient-1);
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .logo-icon svg { width: 22px; height: 22px; fill: white; }

    .logo-text {
      font-size: 22px;
      font-weight: 800;
      color: var(--text);
      letter-spacing: -0.02em;
    }

    .brand-content { max-width: 500px; }

    .brand-headline {
      font-size: 48px;
      font-weight: 800;
      line-height: 1.1;
      letter-spacing: -0.03em;
      margin-bottom: 20px;
      background: linear-gradient(135deg, #f1f5f9 0%, #94a3b8 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .brand-sub {
      font-size: 17px;
      line-height: 1.65;
      color: var(--text-muted);
      margin-bottom: 40px;
    }

    /* Step Progress (Left Side) */
    .step-indicator {
      display: flex;
      flex-direction: column;
      gap: 0;
    }

    .step-track {
      display: flex;
      flex-direction: column;
      gap: 0;
    }

    .step-item {
      display: flex;
      align-items: flex-start;
      gap: 16px;
      position: relative;
    }

    .step-item:not(:last-child)::after {
      content: '';
      position: absolute;
      left: 19px;
      top: 40px;
      width: 2px;
      height: calc(100% - 40px);
      background: var(--border);
      transition: background 0.5s ease;
    }

    .step-item.completed:not(:last-child)::after {
      background: var(--accent);
    }

    .step-dot {
      width: 40px; height: 40px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      font-size: 14px;
      font-weight: 700;
      border: 2px solid var(--border);
      background: var(--bg);
      color: var(--text-subtle);
      transition: all 0.4s ease;
      z-index: 1;
    }

    .step-item.active .step-dot {
      border-color: var(--accent);
      background: var(--accent);
      color: white;
      box-shadow: 0 0 0 4px rgba(99,102,241,0.2);
    }

    .step-item.completed .step-dot {
      border-color: var(--green);
      background: var(--green);
      color: white;
    }

    .step-item.completed .step-dot::after {
      content: '✓';
      font-size: 16px;
    }

    .step-item:not(.completed):not(.active) .step-dot::before {
      content: attr(data-num);
    }

    .step-content {
      padding-bottom: 32px;
    }

    .step-title {
      font-size: 16px;
      font-weight: 700;
      margin-bottom: 4px;
      transition: color 0.3s;
    }

    .step-item.active .step-title { color: var(--text); }
    .step-item.completed .step-title { color: var(--green); }
    .step-item:not(.active):not(.completed) .step-title { color: var(--text-subtle); }

    .step-desc {
      font-size: 13px;
      color: var(--text-muted);
      line-height: 1.5;
    }

    /* Right Panel (Form) */
    .right-panel {
      flex: 0.9;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 40px 32px;
      position: relative;
    }

    .form-card {
      width: 100%;
      max-width: 440px;
    }

    .form-header {
      text-align: center;
      margin-bottom: 28px;
    }

    .form-header h2 {
      font-size: 26px;
      font-weight: 800;
      letter-spacing: -0.02em;
      margin-bottom: 6px;
    }

    .form-header p {
      color: var(--text-muted);
      font-size: 15px;
    }

    /* Step Containers */
    .step-container {
      display: none;
    }

    .step-container.active {
      display: block;
      animation: fadeSlideIn 0.4s ease;
    }

    @keyframes fadeSlideIn {
      from { opacity: 0; transform: translateX(20px); }
      to { opacity: 1; transform: translateX(0); }
    }

    /* Form Elements */
    .form { display: flex; flex-direction: column; gap: 16px; }

    .form-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }

    @media (max-width: 500px) {
      .form-row { grid-template-columns: 1fr; }
    }

    .form-group { display: flex; flex-direction: column; gap: 7px; }

    .form-label {
      font-size: 13px;
      font-weight: 600;
      color: #94a3b8;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .form-label .required { color: var(--red); }

    .input-wrapper { position: relative; }

    .input-icon {
      position: absolute;
      left: 14px;
      top: 50%;
      transform: translateY(-50%);
      color: var(--text-subtle);
      pointer-events: none;
      transition: color 0.2s;
    }

    .input-icon svg { width: 18px; height: 18px; display: block; }

    .form-input {
      width: 100%;
      padding: 13px 14px 13px 44px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      color: var(--text);
      font-size: 15px;
      font-family: inherit;
      transition: all 0.2s;
      outline: none;
    }

    .form-input::placeholder { color: var(--text-subtle); }
    .form-input:hover { border-color: var(--border-2); }
    .form-input:focus {
      border-color: var(--accent);
      background: rgba(99,102,241,0.05);
      box-shadow: 0 0 0 3px var(--accent-glow);
    }
    .form-input:focus ~ .input-icon,
    .form-input:focus + .input-icon { color: var(--accent-light); }

    .form-input.error {
      border-color: var(--red);
      background: var(--red-bg);
    }

    .form-input.success {
      border-color: var(--green);
      background: var(--green-bg);
    }

    /* Password strength */
    .strength-bar {
      height: 4px;
      border-radius: 999px;
      background: rgba(255,255,255,0.05);
      margin-top: 8px;
      overflow: hidden;
    }

    .strength-fill {
      height: 100%;
      border-radius: 999px;
      width: 0%;
      transition: all 0.4s ease;
    }

    .strength-fill.weak { width: 25%; background: var(--red); }
    .strength-fill.fair { width: 50%; background: var(--yellow); }
    .strength-fill.good { width: 75%; background: var(--blue); }
    .strength-fill.strong { width: 100%; background: var(--green); }

    .strength-text {
      display: flex;
      justify-content: space-between;
      margin-top: 6px;
      font-size: 12px;
    }

    .strength-label { font-weight: 600; }
    .strength-label.weak { color: var(--red); }
    .strength-label.fair { color: var(--yellow); }
    .strength-label.good { color: var(--blue); }
    .strength-label.strong { color: var(--green); }

    .strength-hint { color: var(--text-muted); }

    /* Requirements checklist */
    .requirements {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
      margin-top: 4px;
    }

    .req-item {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      color: var(--text-muted);
      transition: color 0.2s;
    }

    .req-item.met { color: var(--green); }
    .req-item.met .req-dot { background: var(--green); border-color: var(--green); }

    .req-dot {
      width: 16px; height: 16px;
      border-radius: 50%;
      border: 2px solid var(--border-2);
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s;
      flex-shrink: 0;
    }

    .req-dot svg { width: 9px; height: 9px; stroke: white; opacity: 0; transform: scale(0.5); transition: all 0.2s; }
    .req-item.met .req-dot svg { opacity: 1; transform: scale(1); }

    /* Password toggle */
    .password-wrapper { position: relative; }

    .password-wrapper .form-input { padding-right: 44px; }

    .pw-toggle {
      position: absolute;
      right: 14px;
      top: 50%;
      transform: translateY(-50%);
      background: none;
      border: none;
      color: var(--text-subtle);
      cursor: pointer;
      padding: 4px;
      display: flex;
      transition: color 0.2s;
      border-radius: 6px;
    }

    .pw-toggle:hover { color: var(--text-muted); }
    .pw-toggle svg { width: 18px; height: 18px; display: block; }

    /* 2FA Code Input */
    .code-display {
      display: flex;
      justify-content: center;
      gap: 10px;
      margin: 20px 0;
    }

    .code-digit {
      width: 52px; height: 60px;
      text-align: center;
      font-size: 26px;
      font-weight: 700;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      color: var(--text);
      font-family: inherit;
      transition: all 0.2s;
      outline: none;
    }

    .code-digit:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--accent-glow);
    }

    .code-digit.filled {
      border-color: var(--accent);
      background: rgba(99,102,241,0.08);
    }

    /* QR Code placeholder */
    .qr-section {
      display: flex;
      align-items: center;
      gap: 20px;
      padding: 20px;
      background: rgba(255,255,255,0.02);
      border: 1px solid var(--border);
      border-radius: 16px;
      margin-bottom: 16px;
    }

    .qr-box {
      width: 100px; height: 100px;
      border-radius: 12px;
      background: white;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      overflow: hidden;
    }

    .qr-box svg { width: 80px; height: 80px; }

    .qr-info h4 { font-size: 15px; font-weight: 700; margin-bottom: 4px; }
    .qr-info p { font-size: 13px; color: var(--text-muted); line-height: 1.5; }
    .qr-info code {
      font-family: 'Courier New', monospace;
      background: var(--surface-2);
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 13px;
    }

    /* Backup codes */
    .backup-codes {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 8px;
      padding: 16px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      margin: 16px 0;
    }

    .backup-code {
      font-family: 'Courier New', monospace;
      font-size: 13px;
      font-weight: 700;
      color: var(--text-muted);
      text-align: center;
      padding: 6px;
      background: var(--surface-3);
      border-radius: 6px;
    }

    /* 2FA Method selector */
    .method-options {
      display: flex;
      flex-direction: column;
      gap: 12px;
      margin-bottom: 20px;
    }

    .method-option {
      display: flex;
      align-items: center;
      gap: 14px;
      padding: 16px;
      background: var(--surface);
      border: 2px solid var(--border);
      border-radius: 14px;
      cursor: pointer;
      transition: all 0.2s;
    }

    .method-option:hover { border-color: var(--border-2); }
    .method-option.selected { border-color: var(--accent); background: rgba(99,102,241,0.08); }

    .method-icon {
      width: 44px; height: 44px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }

    .method-icon.app { background: rgba(99,102,241,0.15); color: var(--accent-light); }
    .method-icon.sms { background: rgba(6,182,212,0.15); color: var(--accent-2); }
    .method-icon svg { width: 22px; height: 22px; }

    .method-text h4 { font-size: 15px; font-weight: 700; margin-bottom: 2px; }
    .method-text p { font-size: 13px; color: var(--text-muted); }

    .method-radio {
      width: 20px; height: 20px;
      border-radius: 50%;
      border: 2px solid var(--border-2);
      margin-left: auto;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s;
      flex-shrink: 0;
    }

    .method-option.selected .method-radio {
      border-color: var(--accent);
    }

    .method-radio::after {
      content: '';
      width: 10px; height: 10px;
      border-radius: 50%;
      background: var(--accent);
      opacity: 0;
      transform: scale(0);
      transition: all 0.2s;
    }

    .method-option.selected .method-radio::after {
      opacity: 1;
      transform: scale(1);
    }

    /* SMS input */
    .sms-input-row {
      display: flex;
      gap: 10px;
      margin-bottom: 16px;
    }

    .sms-input-row .form-input { flex: 1; }

    .resend-btn {
      padding: 13px 16px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      color: var(--accent-light);
      font-size: 13px;
      font-weight: 600;
      font-family: inherit;
      cursor: pointer;
      transition: all 0.2s;
      white-space: nowrap;
    }

    .resend-btn:hover { border-color: var(--accent); }
    .resend-btn:disabled { opacity: 0.5; cursor: not-allowed; }

    /* Submit button */
    .submit-btn {
      width: 100%;
      padding: 14px;
      background: var(--gradient-1);
      border: none;
      border-radius: 12px;
      color: white;
      font-size: 15px;
      font-weight: 700;
      font-family: inherit;
      cursor: pointer;
      transition: all 0.2s;
      position: relative;
      overflow: hidden;
    }

    .submit-btn:hover {
      transform: translateY(-1px);
      box-shadow: 0 8px 25px rgba(99,102,241,0.35);
    }

    .submit-btn:active { transform: translateY(0); }

    .submit-btn.loading { color: transparent; pointer-events: none; }

    .submit-btn .spinner {
      position: absolute;
      top: 50%; left: 50%;
      transform: translate(-50%, -50%);
      width: 22px; height: 22px;
      border: 2.5px solid rgba(255,255,255,0.3);
      border-top-color: white;
      border-radius: 50%;
      opacity: 0;
      transition: opacity 0.2s;
    }

    .submit-btn.loading .spinner { opacity: 1; animation: spin 0.7s linear infinite; }

    @keyframes spin { to { transform: translate(-50%, -50%) rotate(360deg); } }

    .submit-btn.outline {
      background: transparent;
      border: 1px solid var(--border-2);
      color: var(--text-muted);
    }

    .submit-btn.outline:hover { background: var(--surface); color: var(--text); }

    /* Divider */
    .divider {
      display: flex;
      align-items: center;
      gap: 14px;
      margin: 16px 0;
      color: var(--text-subtle);
      font-size: 13px;
    }

    .divider::before, .divider::after {
      content: '';
      flex: 1;
      height: 1px;
      background: var(--border);
    }

    /* Social buttons */
    .social-btns {
      display: flex;
      gap: 10px;
    }

    .social-btn {
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 11px 14px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      color: var(--text);
      font-size: 14px;
      font-weight: 600;
      font-family: inherit;
      cursor: pointer;
      transition: all 0.2s;
    }

    .social-btn:hover { background: var(--surface-2); border-color: var(--border-2); transform: translateY(-1px); }
    .social-btn svg { width: 20px; height: 20px; }

    /* Success state */
    .success-state {
      display: none;
      flex-direction: column;
      align-items: center;
      text-align: center;
      padding: 20px 0;
    }

    .success-state.show { display: flex; animation: fadeSlideIn 0.5s ease; }

    .success-icon {
      width: 80px; height: 80px;
      border-radius: 50%;
      background: var(--green-bg);
      border: 2px solid var(--green-border);
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 20px;
      animation: popIn 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    }

    @keyframes popIn {
      from { opacity: 0; transform: scale(0.5); }
      to { opacity: 1; transform: scale(1); }
    }

    .success-icon svg { width: 36px; height: 36px; stroke: var(--green); }

    .success-state h3 { font-size: 24px; font-weight: 800; margin-bottom: 8px; }
    .success-state p { color: var(--text-muted); font-size: 15px; line-height: 1.5; max-width: 320px; margin: 0 auto 20px; }

    .success-detail {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 14px 20px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      font-size: 14px;
      color: var(--text-muted);
      margin-bottom: 20px;
    }

    .success-detail svg { width: 20px; height: 20px; color: var(--accent-light); flex-shrink: 0; }

    /* Alert */
    .alert {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      padding: 12px 14px;
      border-radius: 12px;
      font-size: 14px;
      margin-bottom: 12px;
      animation: shake 0.4s ease;
    }

    .alert.error {
      background: var(--red-bg);
      border: 1px solid var(--red-border);
      color: #fca5a5;
    }

    .alert.success {
      background: var(--green-bg);
      border: 1px solid var(--green-border);
      color: #86efac;
    }

    .alert svg { width: 18px; height: 18px; flex-shrink: 0; }

    @keyframes shake {
      0%, 100% { transform: translateX(0); }
      20% { transform: translateX(-6px); }
      40% { transform: translateX(6px); }
      60% { transform: translateX(-4px); }
      80% { transform: translateX(4px); }
    }

    /* Footer */
    .form-footer {
      text-align: center;
      margin-top: 24px;
      font-size: 14px;
      color: var(--text-muted);
    }

    .form-footer a { color: var(--accent-light); text-decoration: none; font-weight: 600; }
    .form-footer a:hover { text-decoration: underline; }

    /* Step count badge */
    .step-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 12px;
      background: rgba(99,102,241,0.1);
      border: 1px solid rgba(99,102,241,0.2);
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      color: var(--accent-light);
      margin-bottom: 16px;
    }

    .step-badge .total { color: var(--text-muted); font-weight: 500; }

    /* Timer */
    .timer {
      text-align: center;
      font-size: 13px;
      color: var(--text-muted);
      margin-top: 12px;
    }

    .timer strong { color: var(--accent-light); font-weight: 700; }

    /* Animations */
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .form-group { animation: fadeIn 0.4s ease backwards; }
    .form-group:nth-child(1) { animation-delay: 0.05s; }
    .form-group:nth-child(2) { animation-delay: 0.1s; }
    .form-group:nth-child(3) { animation-delay: 0.15s; }
    .form-group:nth-child(4) { animation-delay: 0.2s; }

    @media (max-width: 600px) {
      .right-panel { padding: 24px 16px; align-items: flex-start; }
      .brand-headline { font-size: 36px; }
      .code-digit { width: 44px; height: 52px; font-size: 22px; }
      .code-display { gap: 7px; }
      .qr-section { flex-direction: column; text-align: center; }
    }
  </style>
</head>
<body>

  <!-- Animated Background -->
  <div class="bg-canvas">
    <div class="bg-orb bg-orb-1"></div>
    <div class="bg-orb bg-orb-2"></div>
    <div class="bg-orb bg-orb-3"></div>
  </div>
  <div class="bg-grid"></div>

  <div class="split">

    <!-- Left Panel -->
    <div class="left-panel">
      <a href="#" class="brand-logo">
        <div class="logo-icon">
          <svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
        </div>
        <span class="logo-text">Nexus</span>
      </a>

      <div class="brand-content">
        <h1 class="brand-headline">Join the future of intelligent investing.</h1>
        <p class="brand-sub">Create your account in minutes. Advanced security with two-factor authentication protects everything.</p>

        <div class="step-indicator">
          <div class="step-track">

            <div class="step-item active" id="step-ind-1">
              <div class="step-dot" data-num="1"></div>
              <div class="step-content">
                <div class="step-title">Create Account</div>
                <div class="step-desc">Enter your name, email, and a strong password</div>
              </div>
            </div>

            <div class="step-item" id="step-ind-2">
              <div class="step-dot" data-num="2"></div>
              <div class="step-content">
                <div class="step-title">Verify Email</div>
                <div class="step-desc">Confirm your email address with a 6-digit code</div>
              </div>
            </div>

            <div class="step-item" id="step-ind-3">
              <div class="step-dot" data-num="3"></div>
              <div class="step-content">
                <div class="step-title">Two-Factor Auth</div>
                <div class="step-desc">Secure your account with an authenticator app or SMS</div>
              </div>
            </div>

            <div class="step-item" id="step-ind-4">
              <div class="step-dot" data-num="4"></div>
              <div class="step-content">
                <div class="step-title">You're All Set!</div>
                <div class="step-desc">Account created. Welcome to Nexus.</div>
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>

    <!-- Right Panel -->
    <div class="right-panel">
      <div class="form-card">

        <!-- STEP 1: Account Creation -->
        <div class="step-container active" id="step-1">

          <div class="form-header">
            <div class="step-badge">Step 1 of 4 <span class="total">/ Create Account</span></div>
            <h2>Create your account</h2>
            <p>Start your journey with Nexus today</p>
          </div>

          <div id="step1Alert"></div>

          <div class="social-btns">
            <button class="social-btn" type="button">
              <svg viewBox="0 0 24 24"><path fill="#fff" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#fff" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#fff" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#fff" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
              Google
            </button>
            <button class="social-btn" type="button">
              <svg viewBox="0 0 24 24" fill="#fff"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
              Apple
            </button>
          </div>

          <div class="divider">or</div>

          <form class="form" id="formStep1" novalidate>

            <div class="form-row">
              <div class="form-group">
                <label class="form-label">First name <span class="required">*</span></label>
                <div class="input-wrapper">
                  <span class="input-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                  </span>
                  <input type="text" class="form-input" id="firstName" placeholder="Sarah" autocomplete="given-name" required>
                </div>
              </div>
              <div class="form-group">
                <label class="form-label">Last name <span class="required">*</span></label>
                <div class="input-wrapper">
                  <span class="input-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                  </span>
                  <input type="text" class="form-input" id="lastName" placeholder="Kim" autocomplete="family-name" required>
                </div>
              </div>
            </div>

            <div class="form-group">
              <label class="form-label">Work email <span class="required">*</span></label>
              <div class="input-wrapper">
                <span class="input-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
                </span>
                <input type="email" class="form-input" id="email" placeholder="sarah@company.com" autocomplete="email" required>
              </div>
            </div>

            <div class="form-group">
              <label class="form-label">Password <span class="required">*</span></label>
              <div class="password-wrapper">
                <input type="password" class="form-input" id="password" placeholder="Create a strong password" autocomplete="new-password" required>
                <button type="button" class="pw-toggle" id="pwToggle1" aria-label="Show password">
                  <svg class="eye-open" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                  <svg class="eye-closed" style="display:none" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                </button>
              </div>
              <div class="strength-bar">
                <div class="strength-fill" id="strengthFill"></div>
              </div>
              <div class="strength-text">
                <span class="strength-label" id="strengthLabel">—</span>
                <span class="strength-hint">Use 12+ characters with mixed characters</span>
              </div>
            </div>

            <!-- Password requirements -->
            <div class="requirements" id="pwRequirements">
              <div class="req-item" id="req-length">
                <div class="req-dot"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></div>
                12+ characters
              </div>
              <div class="req-item" id="req-upper">
                <div class="req-dot"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></div>
                Uppercase letter
              </div>
              <div class="req-item" id="req-lower">
                <div class="req-dot"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></div>
                Lowercase letter
              </div>
              <div class="req-item" id="req-number">
                <div class="req-dot"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></div>
                Number
              </div>
              <div class="req-item" id="req-special">
                <div class="req-dot"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></div>
                Special character
              </div>
              <div class="req-item" id="req-match">
                <div class="req-dot"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></div>
                Passwords match
              </div>
            </div>

            <div class="form-group">
              <label class="form-label">Confirm password <span class="required">*</span></label>
              <div class="password-wrapper">
                <input type="password" class="form-input" id="confirmPassword" placeholder="Confirm your password" autocomplete="new-password" required>
                <button type="button" class="pw-toggle" id="pwToggle2" aria-label="Show password">
                  <svg class="eye-open" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                  <svg class="eye-closed" style="display:none" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                </button>
              </div>
            </div>

            <div class="form-group">
              <label class="form-label">I agree to the</label>
              <div style="display:flex;align-items:flex-start;gap:10px;margin-top:4px;">
                <input type="checkbox" id="terms" style="margin-top:3px;accent-color:var(--accent);" required>
                <span style="font-size:14px;color:var(--text-muted);line-height:1.5;">
                  I agree to the <a href="#" style="color:var(--accent-light);text-decoration:none;">Terms of Service</a> and <a href="#" style="color:var(--accent-light);text-decoration:none;">Privacy Policy</a>
                </span>
              </div>
            </div>

            <button type="submit" class="submit-btn" id="btnStep1">
              Create Account
              <div class="spinner"></div>
            </button>

          </form>

          <div class="form-footer">
            Already have an account? <a href="#">Sign in</a>
          </div>
        </div>

        <!-- STEP 2: Email Verification -->
        <div class="step-container" id="step-2">
          <div class="form-header">
            <div class="step-badge">Step 2 of 4 <span class="total">/ Verify Email</span></div>
            <h2>Check your inbox</h2>
            <p>We've sent a 6-digit verification code to <strong id="displayEmail" style="color:var(--accent-light);">sarah@company.com</strong></p>
          </div>

          <div id="step2Alert"></div>

          <div class="code-display" id="emailCodeDisplay">
            <input type="text" class="code-digit" maxlength="1" data-index="0" inputmode="numeric" pattern="[0-9]">
            <input type="text" class="code-digit" maxlength="1" data-index="1" inputmode="numeric" pattern="[0-9]">
            <input type="text" class="code-digit" maxlength="1" data-index="2" inputmode="numeric" pattern="[0-9]">
            <input type="text" class="code-digit" maxlength="1" data-index="3" inputmode="numeric" pattern="[0-9]">
            <input type="text" class="code-digit" maxlength="1" data-index="4" inputmode="numeric" pattern="[0-9]">
            <input type="text" class="code-digit" maxlength="1" data-index="5" inputmode="numeric" pattern="[0-9]">
          </div>

          <div class="timer">
            Resend code in <strong id="emailTimer">60</strong>s
          </div>

          <button type="button" class="submit-btn" id="btnStep2" style="margin-top:20px;" disabled>
            Verify Email
            <div class="spinner"></div>
          </button>

          <button type="button" class="submit-btn outline" id="resendBtn" disabled style="margin-top:10px;">
            Resend Verification Code
          </button>

          <div class="form-footer" style="margin-top:20px;">
            <a href="#" onclick="goToStep(1); return false;">← Back to sign up</a>
          </div>
        </div>

        <!-- STEP 3: 2FA Setup -->
        <div class="step-container" id="step-3">
          <div class="form-header">
            <div class="step-badge">Step 3 of 4 <span class="total">/ Secure Account</span></div>
            <h2>Set up Two-Factor Auth</h2>
            <p>Add an extra layer of security to protect your account</p>
          </div>

          <div id="step3Alert"></div>

          <!-- Method Selection -->
          <div class="method-options" id="methodOptions">
            <div class="method-option selected" data-method="app" onclick="selectMethod(this)">
              <div class="method-icon app">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg>
              </div>
              <div class="method-text">
                <h4>Authenticator App</h4>
                <p>Use Google Authenticator, Authy, or any TOTP app</p>
              </div>
              <div class="method-radio"></div>
            </div>

            <div class="method-option" data-method="sms" onclick="selectMethod(this)">
              <div class="method-icon sms">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
              </div>
              <div class="method-text">
                <h4>Text Message (SMS)</h4>
                <p>Receive a code via text message</p>
              </div>
              <div class="method-radio"></div>
            </div>
          </div>

          <!-- Authenticator App Section -->
          <div id="appSection">
            <div class="qr-section">
              <div class="qr-box">
                <!-- QR Code SVG -->
                <svg viewBox="0 0 80 80" xmlns="http://www.w3.org/2000/svg">
                  <rect width="80" height="80" fill="white"/>
                  <rect x="4" y="4" width="24" height="24" fill="#060912"/>
                  <rect x="8" y="8" width="16" height="16" fill="white"/>
                  <rect x="12" y="12" width="8" height="8" fill="#060912"/>
                  <rect x="52" y="4" width="24" height="24" fill="#060912"/>
                  <rect x="56" y="8" width="16" height="16" fill="white"/>
                  <rect x="60" y="12" width="8" height="8" fill="#060912"/>
                  <rect x="4" y="52" width="24" height="24" fill="#060912"/>
                  <rect x="8" y="56" width="16" height="16" fill="white"/>
                  <rect x="12" y="60" width="8" height="8" fill="#060912"/>
                  <rect x="32" y="4" width="4" height="4" fill="#060912"/>
                  <rect x="40" y="4" width="4" height="4" fill="#060912"/>
                  <rect x="48" y="4" width="4" height="4" fill="#060912"/>
                  <rect x="32" y="12" width="4" height="4" fill="#060912"/>
                  <rect x="44" y="12" width="4" height="4" fill="#060912"/>
                  <rect x="36" y="20" width="4" height="4" fill="#060912"/>
                  <rect x="44" y="20" width="4" height="4" fill="#060912"/>
                  <rect x="52" y="32" width="4" height="4" fill="#060912"/>
                  <rect x="60" y="32" width="4" height="4" fill="#060912"/>
                  <rect x="68" y="32" width="4" height="4" fill="#060912"/>
                  <rect x="56" y="40" width="4" height="4" fill="#060912"/>
                  <rect x="64" y="40" width="4" height="4" fill="#060912"/>
                  <rect x="56" y="48" width="4" height="4" fill="#060912"/>
                  <rect x="64" y="48" width="4" height="4" fill="#060912"/>
                  <rect x="68" y="56" width="4" height="4" fill="#060912"/>
                  <rect x="4" y="32" width="4" height="4" fill="#060912"/>
                  <rect x="8" y="36" width="4" height="4" fill="#060912"/>
                  <rect x="16" y="32" width="4" height="4" fill="#060912"/>
                  <rect x="4" y="44" width="4" height="4" fill="#060912"/>
                  <rect x="12" y="44" width="4" height="4" fill="#060912"/>
                  <rect x="4" y="68" width="4" height="4" fill="#060912"/>
                  <rect x="12" y="68" width="4" height="4" fill="#060912"/>
                  <rect x="20" y="68" width="4" height="4" fill="#060912"/>
                  <rect x="36" y="32" width="4" height="4" fill="#060912"/>
                  <rect x="40" y="28" width="4" height="4" fill="#060912"/>
                  <rect x="36" y="40" width="4" height="4" fill="#060912"/>
                  <rect x="32" y="48" width="4" height="4" fill="#060912"/>
                  <rect x="40" y="52" width="4" height="4" fill="#060912"/>
                  <rect x="48" y="56" width="4" height="4" fill="#060912"/>
                  <rect x="36" y="60" width="4" height="4" fill="#060912"/>
                  <rect x="44" y="64" width="4" height="4" fill="#060912"/>
                  <rect x="52" y="68" width="4" height="4" fill="#060912"/>
                  <rect x="60" y="64" width="4" height="4" fill="#060912"/>
                  <rect x="68" y="68" width="4" height="4" fill="#060912"/>
                </svg>
              </div>
              <div class="qr-info">
                <h4>Scan this QR code</h4>
                <p>Open your authenticator app (Google Authenticator, Authy, etc.) and scan the code below.</p>
                <p style="margin-top:8px;">Or enter this code manually: <code>JBSWY3DPEHPK3PXP</code></p>
              </div>
            </div>

            <div class="form-group">
              <label class="form-label">Enter the 6-digit code <span class="required">*</span></label>
              <div class="code-display" id="appCodeDisplay">
                <input type="text" class="code-digit" maxlength="1" data-index="0" inputmode="numeric" pattern="[0-9]">
                <input type="text" class="code-digit" maxlength="1" data-index="1" inputmode="numeric" pattern="[0-9]">
                <input type="text" class="code-digit" maxlength="1" data-index="2" inputmode="numeric" pattern="[0-9]">
                <input type="text" class="code-digit" maxlength="1" data-index="3" inputmode="numeric" pattern="[0-9]">
                <input type="text" class="code-digit" maxlength="1" data-index="4" inputmode="numeric" pattern="[0-9]">
                <input type="text" class="code-digit" maxlength="1" data-index="5" inputmode="numeric" pattern="[0-9]">
              </div>
            </div>

            <button type="button" class="submit-btn" id="btnStep3App" style="margin-top:4px;" disabled>
              Enable Authenticator
              <div class="spinner"></div>
            </button>
          </div>

          <!-- SMS Section (hidden by default) -->
          <div id="smsSection" style="display:none;">
            <div class="form-group">
              <label class="form-label">Phone number <span class="required">*</span></label>
              <div class="input-wrapper">
                <span class="input-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
                </span>
                <input type="tel" class="form-input" id="phoneNumber" placeholder="+1 (555) 000-0000" autocomplete="tel">
              </div>
            </div>

            <button type="button" class="submit-btn" id="sendSmsBtn">
              Send SMS Code
              <div class="spinner"></div>
            </button>

            <div id="smsCodeSection" style="display:none; margin-top:16px;">
              <div class="form-group">
                <label class="form-label">Enter the 6-digit code from SMS <span class="required">*</span></label>
                <div class="code-display" id="smsCodeDisplay">
                  <input type="text" class="code-digit" maxlength="1" data-index="0" inputmode="numeric" pattern="[0-9]">
                  <input type="text" class="code-digit" maxlength="1" data-index="1" inputmode="numeric" pattern="[0-9]">
                  <input type="text" class="code-digit" maxlength="1" data-index="2" inputmode="numeric" pattern="[0-9]">
                  <input type="text" class="code-digit" maxlength="1" data-index="3" inputmode="numeric" pattern="[0-9]">
                  <input type="text" class="code-digit" maxlength="1" data-index="4" inputmode="numeric" pattern="[0-9]">
                  <input type="text" class="code-digit" maxlength="1" data-index="5" inputmode="numeric" pattern="[0-9]">
                </div>
              </div>

              <div class="timer">
                Resend code in <strong id="smsTimer">60</strong>s
              </div>

              <button type="button" class="submit-btn" id="btnStep3Sms" style="margin-top:12px;" disabled>
                Verify & Enable 2FA
                <div class="spinner"></div>
              </button>
            </div>
          </div>

          <!-- Backup Codes -->
          <div id="backupCodesSection" style="display:none;">
            <div class="alert success" style="margin-top:16px;">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
              <span>2FA enabled! Save your backup codes below — you can use them if you lose access to your authenticator.</span>
            </div>

            <div class="backup-codes">
              <div class="backup-code">XKCD-7291</div>
              <div class="backup-code">PLMN-3847</div>
              <div class="backup-code">QRST-1563</div>
              <div class="backup-code">BVWY-9024</div>
              <div class="backup-code">HJEF-6381</div>
              <div class="backup-code">AMNP-4729</div>
              <div class="backup-code">TGKZ-8156</div>
              <div class="backup-code">DLSQ-2934</div>
            </div>

            <button type="button" class="submit-btn" id="btnBackupCodes">
              I've Saved My Codes — Continue
              <div class="spinner"></div>
            </button>
          </div>

          <div class="form-footer" style="margin-top:16px;">
            <a href="#" onclick="goToStep(2); return false;">← Back</a>
          </div>
        </div>

        <!-- STEP 4: Success -->
        <div class="step-container" id="step-4">
          <div class="success-state show">
            <div class="success-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            </div>
            <h3>You're all set!</h3>
            <p>Your account has been created and secured with two-factor authentication. Welcome to Nexus.</p>

            <div class="success-detail">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
              <div>
                Signed in as <strong style="color:var(--text);" id="successEmail">sarah@company.com</strong>
              </div>
            </div>

            <div class="success-detail" style="background:var(--green-bg);border-color:var(--green-border);">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>
              <div>
                Two-factor authentication is <strong style="color:var(--green);">enabled</strong>
              </div>
            </div>

            <button type="button" class="submit-btn" onclick="alert('Redirecting to dashboard...')">
              Go to Dashboard →
            </button>

            <div class="form-footer" style="margin-top:16px;">
              <a href="#" onclick="location.reload(); return false;">Create another account</a>
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>

  <script>
    // ===== STATE =====
    let currentStep = 1;
    let selectedMethod = 'app';
    let emailTimerInterval;
    let smsTimerInterval;

    // ===== PASSWORD VISIBILITY TOGGLE =====
    function setupPwToggle(toggleId, inputId) {
      const toggle = document.getElementById(toggleId);
      const input = document.getElementById(inputId) || document.querySelector(`#${toggleId}`).closest('.password-wrapper').querySelector('input');
      if (!toggle || !input) return;
      toggle.addEventListener('click', () => {
        const isPw = input.type === 'password';
        input.type = isPw ? 'text' : 'password';
        toggle.querySelector('.eye-open').style.display = isPw ? 'none' : 'block';
        toggle.querySelector('.eye-closed').style.display = isPw ? 'block' : 'none';
      });
    }

    setupPwToggle('pwToggle1', 'password');
    setupPwToggle('pwToggle2', 'confirmPassword');

    // ===== PASSWORD STRENGTH =====
    const passwordInput = document.getElementById('password');
    const confirmInput = document.getElementById('confirmPassword');
    const strengthFill = document.getElementById('strengthFill');
    const strengthLabel = document.getElementById('strengthLabel');

    function checkStrength(pw) {
      const checks = {
        length: pw.length >= 12,
        upper: /[A-Z]/.test(pw),
        lower: /[a-z]/.test(pw),
        number: /[0-9]/.test(pw),
        special: /[^A-Za-z0-9]/.test(pw)
      };

      const count = Object.values(checks).filter(Boolean).length;

      // Update requirements
      document.getElementById('req-length').className = 'req-item' + (checks.length ? ' met' : '');
      document.getElementById('req-upper').className = 'req-item' + (checks.upper ? ' met' : '');
      document.getElementById('req-lower').className = 'req-item' + (checks.lower ? ' met' : '');
      document.getElementById('req-number').className = 'req-item' + (checks.number ? ' met' : '');
      document.getElementById('req-special').className = 'req-item' + (checks.special ? ' met' : '');
      document.getElementById('req-match').className = 'req-item' + (pw && pw === confirmInput.value ? ' met' : '');

      // Update strength meter
      strengthFill.className = 'strength-fill';
      if (pw.length === 0) { strengthLabel.textContent = '—'; strengthLabel.className = 'strength-label'; return; }

      if (count <= 1) { strengthFill.classList.add('weak'); strengthLabel.textContent = 'Weak'; strengthLabel.className = 'strength-label weak'; }
      else if (count <= 2) { strengthFill.classList.add('fair'); strengthLabel.textContent = 'Fair'; strengthLabel.className = 'strength-label fair'; }
      else if (count <= 3) { strengthFill.classList.add('good'); strengthLabel.textContent = 'Good'; strengthLabel.className = 'strength-label good'; }
      else { strengthFill.classList.add('strong'); strengthLabel.textContent = 'Strong'; strengthLabel.className = 'strength-label strong'; }
    }

    passwordInput.addEventListener('input', () => checkStrength(passwordInput.value));
    confirmInput.addEventListener('input', () => checkStrength(passwordInput.value));

    // ===== CODE INPUT LOGIC =====
    function setupCodeInputs(containerId, onComplete) {
      const container = document.getElementById(containerId);
      if (!container) return;
      const inputs = container.querySelectorAll('.code-digit');

      inputs.forEach((input, idx) => {
        input.addEventListener('input', (e) => {
          const val = e.target.value.replace(/\D/g, '');
          e.target.value = val.slice(-1);
          if (val && idx < inputs.length - 1) {
            inputs[idx + 1].focus();
          }
          e.target.classList.toggle('filled', !!val);
          checkCodeComplete(containerId, onComplete);
        });

        input.addEventListener('keydown', (e) => {
          if (e.key === 'Backspace' && !e.target.value && idx > 0) {
            inputs[idx - 1].focus();
          }
        });

        input.addEventListener('paste', (e) => {
          e.preventDefault();
          const pasted = (e.clipboardData || window.clipboardData).getData('text').replace(/\D/g, '').slice(0, 6);
          pasted.split('').forEach((char, i) => {
            if (inputs[i]) { inputs[i].value = char; inputs[i].classList.add('filled'); }
          });
          if (pasted.length > 0) inputs[Math.min(pasted.length, inputs.length - 1)].focus();
          checkCodeComplete(containerId, onComplete);
        });
      });
    }

    function getCode(containerId) {
      const container = document.getElementById(containerId);
      return Array.from(container.querySelectorAll('.code-digit')).map(i => i.value).join('');
    }

    function clearCode(containerId) {
      const container = document.getElementById(containerId);
      container.querySelectorAll('.code-digit').forEach(i => { i.value = ''; i.classList.remove('filled'); });
    }

    function checkCodeComplete(containerId, callback) {
      const code = getCode(containerId);
      if (code.length === 6) {
        callback(code);
      }
    }

    // Setup all code inputs
    setupCodeInputs('emailCodeDisplay', (code) => {
      document.getElementById('btnStep2').disabled = false;
    });

    setupCodeInputs('appCodeDisplay', (code) => {
      document.getElementById('btnStep3App').disabled = false;
    });

    setupCodeInputs('smsCodeDisplay', (code) => {
      document.getElementById('btnStep3Sms').disabled = false;
    });

    // ===== STEP NAVIGATION =====
    function goToStep(step) {
      // Update indicators
      for (let i = 1; i <= 4; i++) {
        const ind = document.getElementById(`step-ind-${i}`);
        const container = document.getElementById(`step-${i}`);
        ind.classList.remove('active', 'completed');
        if (i < step) ind.classList.add('completed');
        if (i === step) ind.classList.add('active');
        container.classList.remove('active');
      }

      // Show target
      document.getElementById(`step-${step}`).classList.add('active');
      currentStep = step;

      // Scroll to top of form
      window.scrollTo({ top: 0, behavior: 'smooth' });

      // Focus first input
      const firstInput = document.querySelector(`#step-${step} .form-input`);
      if (firstInput) setTimeout(() => firstInput.focus(), 300);
    }

    // ===== STEP 1: SUBMIT =====
    document.getElementById('formStep1').addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('btnStep1');
      const alertEl = document.getElementById('step1Alert');
      alertEl.innerHTML = '';

      const firstName = document.getElementById('firstName').value.trim();
      const lastName = document.getElementById('lastName').value.trim();
      const email = document.getElementById('email').value.trim();
      const password = document.getElementById('password').value;
      const confirm = document.getElementById('confirmPassword').value;
      const terms = document.getElementById('terms').checked;

      // Validation
      if (!firstName || !lastName || !email || !password || !confirm) {
        alertEl.innerHTML = `<div class="alert error"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>Please fill in all required fields.</div>`;
        return;
      }

      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        alertEl.innerHTML = `<div class="alert error"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>Please enter a valid email address.</div>`;
        return;
      }

      if (password.length < 12) {
        alertEl.innerHTML = `<div class="alert error"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>Password must be at least 12 characters.</div>`;
        return;
      }

      if (password !== confirm) {
        alertEl.innerHTML = `<div class="alert error"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>Passwords do not match.</div>`;
        return;
      }

      if (!terms) {
        alertEl.innerHTML = `<div class="alert error"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>You must agree to the Terms of Service.</div>`;
        return;
      }

      // Simulate API call
      btn.classList.add('loading');
      await new Promise(r => setTimeout(r, 1500));
      btn.classList.remove('loading');

      // Update display email
      document.getElementById('displayEmail').textContent = email;
      document.getElementById('successEmail').textContent = email;

      // Start email timer
      startEmailTimer();

      // Go to step 2
      goToStep(2);

      // Auto-fill demo code after a moment (for demo)
      setTimeout(() => {
        const demoCode = '847291';
        const container = document.getElementById('emailCodeDisplay');
        demoCode.split('').forEach((char, i) => {
          const input = container.querySelector(`[data-index="${i}"]`);
          if (input) { input.value = char; input.classList.add('filled'); }
        });
        document.getElementById('btnStep2').disabled = false;
      }, 1000);
    });

    // ===== EMAIL TIMER =====
    function startEmailTimer() {
      let seconds = 60;
      const el = document.getElementById('emailTimer');
      const resendBtn = document.getElementById('resendBtn');
      clearInterval(emailTimerInterval);
      el.textContent = seconds;
      resendBtn.disabled = true;

      emailTimerInterval = setInterval(() => {
        seconds--;
        el.textContent = seconds;
        if (seconds <= 0) {
          clearInterval(emailTimerInterval);
          resendBtn.disabled = false;
          el.textContent = '0';
        }
      }, 1000);
    }

    // ===== STEP 2: VERIFY EMAIL =====
    document.getElementById('btnStep2').addEventListener('click', async () => {
      const btn = document.getElementById('btnStep2');
      const alertEl = document.getElementById('step2Alert');
      alertEl.innerHTML = '';
      const code = getCode('emailCodeDisplay');

      if (code.length !== 6) {
        alertEl.innerHTML = `<div class="alert error"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>Please enter the complete 6-digit code.</div>`;
        return;
      }

      btn.classList.add('loading');
      await new Promise(r => setTimeout(r, 1200));
      btn.classList.remove('loading');

      // For demo: accept any 6-digit code
      alertEl.innerHTML = `<div class="alert success"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>Email verified successfully!</div>`;

      setTimeout(() => goToStep(3), 800);
    });

    // ===== STEP 3: 2FA METHOD SELECTION =====
    function selectMethod(el) {
      document.querySelectorAll('.method-option').forEach(m => m.classList.remove('selected'));
      el.classList.add('selected');
      selectedMethod = el.dataset.method;

      if (selectedMethod === 'app') {
        document.getElementById('appSection').style.display = 'block';
        document.getElementById('smsSection').style.display = 'none';
        document.getElementById('backupCodesSection').style.display = 'none';
      } else {
        document.getElementById('appSection').style.display = 'none';
        document.getElementById('smsSection').style.display = 'block';
        document.getElementById('backupCodesSection').style.display = 'none';
        clearCode('appCodeDisplay');
      }
    }

    // SMS: Send Code
    document.getElementById('sendSmsBtn').addEventListener('click', async () => {
      const btn = document.getElementById('sendSmsBtn');
      const phone = document.getElementById('phoneNumber').value.trim();

      if (!phone || phone.length < 7) {
        return;
      }

      btn.classList.add('loading');
      await new Promise(r => setTimeout(r, 1200));
      btn.classList.remove('loading');

      document.getElementById('smsCodeSection').style.display = 'block';
      startSmsTimer();

      // Auto-fill demo
      setTimeout(() => {
        const demoCode = '583910';
        const container = document.getElementById('smsCodeDisplay');
        demoCode.split('').forEach((char, i) => {
          const input = container.querySelector(`[data-index="${i}"]`);
          if (input) { input.value = char; input.classList.add('filled'); }
        });
        document.getElementById('btnStep3Sms').disabled = false;
      }, 1000);
    });

    function startSmsTimer() {
      let seconds = 60;
      const el = document.getElementById('smsTimer');
      clearInterval(smsTimerInterval);
      el.textContent = seconds;
      smsTimerInterval = setInterval(() => {
        seconds--;
        el.textContent = seconds;
        if (seconds <= 0) clearInterval(smsTimerInterval);
      }, 1000);
    }

    // 2FA App verify
    document.getElementById('btnStep3App').addEventListener('click', async () => {
      const btn = document.getElementById('btnStep3App');
      const alertEl = document.getElementById('step3Alert');
      alertEl.innerHTML = '';
      const code = getCode('appCodeDisplay');

      if (code.length !== 6) return;

      btn.classList.add('loading');
      await new Promise(r => setTimeout(r, 1200));
      btn.classList.remove('loading');

      document.getElementById('appSection').style.display = 'none';
      document.getElementById('backupCodesSection').style.display = 'block';
    });

    // 2FA SMS verify
    document.getElementById('btnStep3Sms').addEventListener('click', async () => {
      const btn = document.getElementById('btnStep3Sms');
      const alertEl = document.getElementById('step3Alert');
      alertEl.innerHTML = '';
      const code = getCode('smsCodeDisplay');

      if (code.length !== 6) return;

      btn.classList.add('loading');
      await new Promise(r => setTimeout(r, 1200));
      btn.classList.remove('loading');

      document.getElementById('smsCodeSection').style.display = 'none';
      document.getElementById('smsSection').querySelector('.form-group').style.display = 'none';
      document.getElementById('sendSmsBtn').style.display = 'none';
      document.getElementById('methodOptions').style.display = 'none';
      document.getElementById('step3Alert').innerHTML = `<div class="alert success"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>2FA enabled via SMS!</div>`;

      setTimeout(() => goToStep(4), 1000);
    });

    // Backup codes — continue
    document.getElementById('btnBackupCodes').addEventListener('click', async () => {
      const btn = document.getElementById('btnBackupCodes');
      btn.classList.add('loading');
      await new Promise(r => setTimeout(r, 1000));
      btn.classList.remove('loading');
      goToStep(4);
    });

    // ===== INITIAL =====
    // Focus first name on load
    document.getElementById('firstName').focus();
  </script>
</body>
</html>
```

---

## Implementation Analysis: File-Based Terms & Privacy Policy Display

### Feasibility

✅ **Fully feasible** — low complexity, no backend changes, zero risk to existing features.

### Current State of the Codebase

| Aspect | Finding |
|--------|---------|
| Terms/Privacy pages | **Do not exist** — no `/terms` or `/privacy` routes |
| Content files | **Do not exist** — no `.md`, `.txt`, or `.html` legal files anywhere |
| Signup form checkbox | **Not implemented** — current form has email + password only, no T&C checkbox |
| Landing page footer | **Dead links** — `Link href="#"` for both Terms of Service and Privacy |
| Markdown rendering | **Not installed** — no `react-markdown`, `remark`, or `rehype` in `package.json` |
| `@tailwindcss/typography` | **Not installed** — no prose styling plugin |
| File-reading pattern | **Not used** — project does not read any `.md`/`.txt`/`.html` files anywhere |
| Content-from-file example | **None** — only `placeholder-images.ts` imports a JSON file; no markdown file patterns exist |

### Approach Options

#### Option A: Server Components + `react-markdown` (Recommended)

Create dedicated `/terms` and `/privacy` routes using Next.js App Router. Store content as Markdown files. Server Components read them via `fs` and render through `react-markdown`.

```
web/public/legal/
  terms.md
  privacy.md

web/src/app/
  terms/page.tsx        →   Server Component, reads terms.md, renders markdown
  privacy/page.tsx      →   Server Component, reads privacy.md, renders markdown
```

**What changes:**
| File | Action | Reason |
|------|--------|--------|
| `web/public/legal/terms.md` | **CREATE** | Terms & Conditions markdown content |
| `web/public/legal/privacy.md` | **CREATE** | Privacy Policy markdown content |
| `web/src/app/terms/page.tsx` | **CREATE** | Route page that reads terms.md and renders through `react-markdown` + `tailwindcss/typography` |
| `web/src/app/privacy/page.tsx` | **CREATE** | Route page that reads privacy.md and renders through `react-markdown` + `tailwindcss/typography` |
| `web/src/app/globals.css` | **MODIFY** | Add `.legal-link` style for in-page anchor links within legal documents |
| `web/src/components/auth/signup-form.tsx` | **MODIFY** | Add T&C checkbox with validation + update `href` of legal links |
| `web/src/app/page.tsx` (footer) | **MODIFY** | Change `href="#"` to `href="/terms"` and `href="/privacy"` |
| `web/package.json` | **MODIFY** | Add `react-markdown`, `remark-gfm`, `@tailwindcss/typography` |
| `web/tailwind.config.ts` | **MODIFY** | Add `@tailwindcss/typography` plugin |

**Dependencies to add:**
- `react-markdown` (~30KB) — renders Markdown as React components
- `remark-gfm` (~8KB) — GitHub Flavored Markdown (tables, strikethrough, URLs)
- `@tailwindcss/typography` (~4KB) — prose styling classes (`.prose`)

**Total new bundle impact:** ~42KB (server-side only for `react-markdown` + `remark-gfm`; `@tailwindcss/typography` is a PostCSS plugin, zero runtime cost).

**Trade-offs:**
- ✅ SEO-friendly — content is in the HTML stream (Server Component)
- ✅ Bookmarkable — `/terms` and `/privacy` are real URLs
- ✅ Accessible — screen readers can navigate to dedicated pages
- ✅ Styled beautifully — `tailwindcss/typography` gives legal-text-prose styling out of the box
- ✅ Clean separation — content files are independent of rendering code
- ⚠️ Adds 3 new npm dependencies (+42KB), though all server-only

#### Option B: Modal Overlay on Signup Page

Keep users on the signup page. Load legal content into a modal/dialog component.

**What changes:**
| File | Action | Reason |
|------|--------|--------|
| `web/public/legal/terms.md` | **CREATE** | Content file |
| `web/public/legal/privacy.md` | **CREATE** | Content file |
| `web/src/components/auth/legal-modal.tsx` | **CREATE** | Reusable modal component that fetches and renders markdown |
| `web/src/components/auth/signup-form.tsx` | **MODIFY** | Add T&C checkbox + open modal on link click |
| `web/src/app/page.tsx` (footer) | **MODIFY** | Change `href="#"` to link to `/terms` and `/privacy` |
| `web/package.json` | **MODIFY** | Add `react-markdown`, `remark-gfm` |
| `web/tailwind.config.ts` | **MODIFY** | (Optional) Add `@tailwindcss/typography` |

**Trade-offs:**
- ✅ User stays in the signup flow — no navigation away
- ⚠️ Not SEO-friendly — content not in HTML unless pre-rendered
- ⚠️ Not bookmarkable — no URL for sharing legal pages
- ⚠️ Modal state must persist across form submission validation
- ❌ Landing page footer links still need destination pages (cannot open a modal from landing page)

#### Option C: Inline Expandable Sections

Render legal content as collapsible `<details>` / `<summary>` elements within the signup form.

**What changes:**
| File | Action | Reason |
|------|--------|--------|
| `web/src/components/auth/signup-form.tsx` | **MODIFY** | Add collapsible T&C and Privacy sections with inline content |

**Trade-offs:**
- ✅ Zero dependencies — no markdown rendering needed
- ⚠️ Cluttered layout — legal text is typically 2000+ words
- ⚠️ Content is hardcoded in the component (no file-based reading)
- ⚠️ Not bookmarkable
- ⚠️ Not SEO-friendly
- ❌ Does not satisfy the requirement of reading from files

### Implementation Chosen: File-Based with Dynamic `[slug]` Route

**What was implemented:**

| Aspect | Decision |
|--------|----------|
| Storage | `web/public/legal/terms.md` and `web/public/legal/privacy.md` |
| Rendering | `web/src/app/legal/[slug]/page.tsx` — dynamic server component reads file via `fs.readFileSync` at request time |
| Markdown | Custom renderer (no external dependency) — handles `#`, `##`, `-`, `**bold**`, `[links](url)` |
| Zero npm deps | No `react-markdown` or `remark-gfm` needed — keeps bundle small |

**Key design choice:** A dynamic `[slug]` route (`/legal/terms`, `/legal/privacy`) instead of two static pages. This means adding a new legal page (e.g. `/legal/cookies`) requires only:
1. Create `web/public/legal/cookies.md`
2. Add `cookies` to the slug allowlist in the page component — no new route file needed

### Files Created

#### 1. Content files

**`web/public/legal/terms.md`** — Full Terms of Service in markdown format.

**`web/public/legal/privacy.md`** — Full Privacy Policy in markdown format.

To update either document, edit the `.md` file directly — no code changes needed. The page reads the file on every request (no caching), so updates are live immediately.

#### 2. Route page

**`web/src/app/legal/[slug]/page.tsx`** — Dynamic server component:
- Reads markdown from `public/legal/{slug}.md` via `fs.readFileSync`
- Renders with a lightweight inline markdown-to-HTML converter
- Handles: headings, bold, lists, links
- Back navigation to `/signup`
- 404 for unknown slugs

#### 3. Modified signup form

**`web/src/components/auth/signup-form.tsx`** — Changes:

- **ADD** T&C checkbox field to the zod schema:
  ```ts
  const formSchema = z.object({
    email:    z.string().email(...),
    password: z.string().min(8, ...),
    terms:    z.literal(true, { errorMap: () => ({ message: 'You must agree to the Terms of Service and Privacy Policy.' }) }),
  });
  ```

- **ADD** T&C checkbox UI between the password field and the submit button:
  ```tsx
  <FormField
    control={form.control}
    name="terms"
    render={({ field }) => (
      <FormItem>
        <div className="flex items-start gap-3">
          <FormControl>
            <input
              type="checkbox"
              checked={field.value}
              onChange={field.onChange}
              className="mt-0.5 accent-indigo-500"
            />
          </FormControl>
          <p className="text-xs text-white/40 leading-relaxed">
            I agree to the{' '}
            <Link href="/terms" target="_blank" className="font-bold text-indigo-400 hover:text-indigo-300 transition-colors">
              Terms of Service
            </Link>{' '}
            and{' '}
            <Link href="/privacy" target="_blank" className="font-bold text-indigo-400 hover:text-indigo-300 transition-colors">
              Privacy Policy
            </Link>
          </p>
        </div>
        <FormMessage className="text-[10px] text-rose-400" />
      </FormItem>
    )}
  />
  ```

#### 4. Modified landing page footer

**`web/src/app/page.tsx`** — Two lines change:
```tsx
<Link href="/terms" className="text-xs hover:underline underline-offset-4" prefetch={false}>
  Terms of Service
</Link>
<Link href="/privacy" className="text-xs hover:underline underline-offset-4" prefetch={false}>
  Privacy
</Link>
```

### What Does NOT Change

| Area | Impact |
|------|--------|
| Backend (FastAPI) | Zero impact — no new endpoints, no DB changes |
| Authenticated routes | Zero impact — `(authenticated)/layout.tsx` unchanged |
| Auth flow (Supabase) | Zero impact for T&C-only change; see 4-Step Flow analysis below for full signup refactor impact |
| API routes (`/api/proxy/...`) | Zero impact |
| Existing tests | Zero impact — no existing signup tests to break |
| CSS utilities (`globals.css`) | Minimal impact — optional `.legal-link` helper only |
| Bundle size for authenticated pages | Zero impact — `react-markdown` is server-only, never shipped to authenticated client |
| Database schema | Zero impact |

### Migration Steps (Ordered)

1. Install dependencies:
   ```bash
   npm install react-markdown remark-gfm
   npm install -D @tailwindcss/typography
   ```
2. Add `@tailwindcss/typography` to `tailwind.config.ts` plugins array
3. Create `web/public/legal/terms.md` with Terms & Conditions content
4. Create `web/public/legal/privacy.md` with Privacy Policy content
5. Create `web/src/app/terms/page.tsx` (Server Component, reads+renders terms.md)
6. Create `web/src/app/privacy/page.tsx` (Server Component, reads+renders privacy.md)
7. Update `web/src/components/auth/signup-form.tsx`:
   - Add `terms: z.literal(true, ...)` to schema
   - Add T&C checkbox field between password and submit button
   - Link to `/terms` and `/privacy` with `target="_blank"`
8. Update `web/src/app/page.tsx` footer links from `href="#"` to `href="/terms"` and `href="/privacy"`
9. Verify end-to-end: signup form → checkbox validation → click legal links → content renders

### Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `react-markdown` breaking change | Low | Medium | Pin to exact version; component is simple, easy to swap |
| Legal content needs frequent updates | Medium | Low | Content is in plain Markdown in `public/` — edit directly, no build step |
| Signup form validation regression | Low | High | Checkbox is additive; existing email/password validation unchanged |
| Dead links missed | Low | Low | Only 2 existing dead links (`page.tsx` footer); grep confirms no others |

---

## The 4-Step Flow Architecture

```
┌─────────────────────────────────────────────┐
│  STEP 1: CREATE ACCOUNT                     │
│  • Name (first + last)                     │
│  • Email                                    │
│  • Password + strength meter                │
│  • Password requirements checklist          │
│  • Confirm password                         │
│  • Terms checkbox                           │
│  • Social signup buttons (Google, Apple)    │
├─────────────────────────────────────────────┤
│  STEP 2: VERIFY EMAIL                       │
│  • 6-digit code input (auto-advance)        │
│  • Countdown timer (60s)                    │
│  • Resend button                           │
│  • Back navigation                          │
├─────────────────────────────────────────────┤
│  STEP 3: TWO-FACTOR AUTHENTICATION           │
│  ┌─────────────────┬──────────────────┐   │
│  │ Authenticator   │ SMS               │   │
│  │ App QR scan     │ Phone input       │   │
│  │ + 6-digit code  │ + 6-digit code    │   │
│  └─────────────────┴──────────────────┘   │
│  • Backup codes display (after setup)       │
├─────────────────────────────────────────────┤
│  STEP 4: SUCCESS / ONBOARDING               │
│  • Animated checkmark                       │
│  • Account confirmed                        │
│  • 2FA status confirmed                     │
│  • CTA: Go to Dashboard                     │
└─────────────────────────────────────────────┘
```

---

## Best Design Patterns Included

### 🔐 Security UX
| Pattern | Implementation |
|---------|---------------|
| **Password strength meter** | Real-time bar + label + color (weak→strong) |
| **Requirements checklist** | 6 requirements with animated checkmarks |
| **Password match check** | Live validation on confirm field |
| **2FA method selector** | Radio-style cards (App vs SMS) |
| **6-digit OTP input** | Auto-advance, paste support, visual feedback |
| **Countdown timers** | Prevents spam, shows resend availability |
| **Backup codes** | 8 codes displayed after 2FA setup |
| **Loading states** | Spinner on all buttons prevents double-submit |

### 🎨 Visual Excellence
| Pattern | Implementation |
|---------|---------------|
| **Step progress indicator** | Left panel with animated line connector |
| **Staggered form animations** | Each field fades in with delay |
| **QR code display** | Realistic QR with manual fallback code |
| **Gradient orbs** | Multi-layer animated background |
| **Glassmorphism** | Subtle blur + transparency on surfaces |
| **Success animation** | Pop-in checkmark with spring easing |
| **Shake on error** | Invalid input triggers shake animation |

### ♿ Accessibility
- All inputs properly labeled
- Required field indicators (`*`)
- Keyboard navigation throughout
- Paste support for OTP codes
- Focus management between steps
- ARIA labels on icon buttons
- Visible focus rings
- Color not sole indicator (icons accompany status)

---

## Key Interactions Explained

### Password Strength Meter
```
User types → Real-time check of:
  ✓ Length ≥ 12 chars
  ✓ Uppercase letter
  ✓ Lowercase letter
  ✓ Number
  ✓ Special character
  ✓ Matches confirm field

Each checkmark animates independently.
Bar grows: Red → Yellow → Blue → Green
```

### 6-Digit Code Input
```
Paste: Splits 6-digit string across all inputs
Backspace: Moves to previous input
Arrow keys: Navigate between inputs
Enter (when complete): Submit form
Auto-advance: After each digit, focus moves right
```

### 2FA Method Selection
```
Authenticator App:      SMS:
  - QR code scan         - Phone number input
  - Manual code entry    - Send SMS button
  - 6-digit TOTP input   - 6-digit code input
                         - Timer + resend
```

---

## What's Different From Other Signup Pages

| Typical Signup | This Design |
|----------------|-------------|
| Single page, all fields at once | 4 focused steps, no overwhelm |
| Password field only | Live strength meter + requirement checklist |
| No 2FA | Full authenticator app + SMS + backup codes |
| Basic form validation | Real-time validation with visual feedback |
| Static background | Animated gradient orbs + grid overlay |
| No progress indication | Visual step indicator with completion states |
| No success state | Full celebration screen with next action |

***Disclaimer: I am an AI, not a lawyer. The following templates are for informational and educational purposes only and do not constitute legal advice. Financial and securities laws (like those enforced by the SEC in the US) are highly complex and strictly regulated. You should have a qualified attorney in your jurisdiction review these documents before publishing them to ensure you are fully protected and compliant.***

Here are comprehensive templates for your **Terms of Service (ToS)** and **Privacy Policy**, specifically tailored for a stock analysis web app with a heavy emphasis on disclaiming financial advice and limiting liability.

---

# TERMS OF SERVICE

**Last Updated: [Date]**

Welcome to **[App Name]** (the "App"), operated by **[Your Company Name/Your Name]** ("we," "us," or "our"). By accessing or using the App, you agree to be bound by these Terms of Service ("Terms"). If you do not agree to these Terms, do not use the App.

### 1. NO FINANCIAL, INVESTMENT, OR TRADING ADVICE (CRITICAL DISCLAIMER)
**THE APP AND ITS CONTENT ARE FOR INFORMATIONAL AND EDUCATIONAL PURPOSES ONLY.** 
*   **Not Financial Advice:** Nothing on the App constitutes financial, investment, trading, legal, or tax advice. We are not registered broker-dealers, investment advisers, or financial planners. 
*   **Do Your Own Research (DYOR):** You acknowledge that you are solely responsible for your own investment decisions. You should not make any investment decisions based solely on the information provided by the App. Always consult with a licensed financial advisor before making any investment decisions.
*   **No Guarantees:** We do not guarantee the accuracy, completeness, or timeliness of any stock analysis, data, or content. Stock markets are volatile, and past performance is not indicative of future results.

### 2. NO LIABILITY FOR INVESTMENT LOSSES
UNDER NO CIRCUMSTANCES SHALL WE BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, INCLUDING BUT NOT LIMITED TO **LOSS OF PROFITS, LOSS OF DATA, LOSS OF GOODWILL, OR ANY INVESTMENT LOSSES OR TRADING LOSSES**, ARISING OUT OF OR IN CONNECTION WITH YOUR USE OF THE APP, WHETHER BASED ON WARRANTY, CONTRACT, TORT, OR ANY OTHER LEGAL THEORY, EVEN IF WE HAVE BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.

### 3. LIMITATION OF LIABILITY
TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, IN NO EVENT SHALL **[Your Company Name]**, ITS AFFILIATES, DIRECTORS, EMPLOYEES, OR AGENTS BE LIABLE FOR ANY DAMAGES WHATSOEVER ARISING OUT OF THE USE OR INABILITY TO USE THE APP. IF YOU ARE DISSATISFIED WITH THE APP, YOUR SOLE AND EXCLUSIVE REMEDY IS TO DISCONTINUE USING THE APP. 

### 4. DATA ACCURACY AND THIRD-PARTY DATA
The App may display stock prices, financial metrics, and other data sourced from third-party providers. We do not control these third parties and make no representations or warranties regarding the accuracy, reliability, or timeliness of their data. Data may be delayed or contain errors. You acknowledge that you use third-party data at your own risk.

### 5. USER ACCOUNTS AND RESPONSIBILITIES
*   **Account Security:** If you create an account, you are responsible for safeguarding your password. You agree not to share your credentials.
*   **Prohibited Conduct:** You agree not to: (a) use the App for any illegal purpose; (b) attempt to hack, reverse engineer, or disrupt the App's infrastructure; (c) scrape or use automated bots to extract data from the App without our express written permission.

### 6. INTELLECTUAL PROPERTY
All content, features, and functionality of the App, including but not limited to text, graphics, logos, software, and code, are the exclusive property of **[Your Company Name]** and are protected by copyright, trademark, and other intellectual property laws.

### 7. TERMINATION
We reserve the right to suspend or terminate your access to the App at our sole discretion, without notice and without liability, for any reason, including if you breach these Terms.

### 8. GOVERNING LAW AND DISPUTE RESOLUTION
These Terms shall be governed by the laws of the State/Country of **[Your State/Country]**, without regard to its conflict of law principles. Any disputes arising out of these Terms or the App shall be resolved through binding arbitration in **[Your City, State]**, except that you may assert claims in small claims court if your claims qualify. **YOU AGREE TO WAIVE YOUR RIGHT TO A JURY TRIAL AND TO PARTICIPATE IN A CLASS ACTION.** *(Note: Consult a lawyer to ensure this arbitration clause is enforceable in your jurisdiction).*

### 9. CHANGES TO TERMS
We reserve the right to modify these Terms at any time. We will notify you of material changes by posting the new Terms on the App and updating the "Last Updated" date. Your continued use of the App constitutes acceptance of the modified Terms.

### 10. CONTACT INFORMATION
If you have any questions about these Terms, please contact us at: **[Your Email Address]**.

---

# PRIVACY POLICY

**Last Updated: [Date]**

**[Your Company Name]** ("we," "us," or "our") respects your privacy and is committed to protecting your personal data. This Privacy Policy explains how we collect, use, and share information when you use **[App Name]**.

### 1. INFORMATION WE COLLECT
We collect information to provide and improve our App. 
*   **Personal Information:** When you register or contact us, we may collect your name, email address, and any other information you voluntarily provide. **We DO NOT collect sensitive financial information, brokerage account credentials, or banking details.**
*   **Usage Data:** We automatically collect certain information when you visit the App, including your IP address, browser type, operating system, referring URLs, and pages viewed.
*   **Cookies and Tracking Technologies:** We use cookies and similar tracking technologies to track activity on our App and hold certain information. You can instruct your browser to refuse all cookies or to indicate when a cookie is being sent.

### 2. HOW WE USE YOUR INFORMATION
We use the collected information for the following purposes:
*   To provide, operate, and maintain the App.
*   To improve, personalize, and expand the App's features.
*   To understand and analyze how you use the App.
*   To communicate with you, either directly or through one of our partners, including for customer service, to provide you with updates and other information relating to the App, and for marketing purposes (only if you have opted in).

### 3. SHARING OF YOUR INFORMATION
We do not sell your personal information. We may share your information in the following situations:
*   **Service Providers:** We may share your information with third-party vendors, service providers, and contractors who perform services on our behalf (e.g., web hosting, email delivery, analytics).
*   **Legal Requirements:** We may disclose your information if required to do so by law or in response to valid requests by public authorities (e.g., a court or a government agency).
*   **Business Transfers:** If we are involved in a merger, acquisition, or sale of all or a portion of our assets, your information may be transferred as part of that transaction.

### 4. DATA SECURITY
We implement reasonable administrative, technical, and physical security measures to protect your personal information. However, no method of transmission over the Internet or method of electronic storage is 100% secure, and we cannot guarantee absolute security.

### 5. YOUR DATA PROTECTION RIGHTS
Depending on your location, you may have the following rights regarding your personal data:
*   The right to access, update, or delete the information we have on you.
*   The right of rectification (to correct inaccurate data).
*   The right to object to the processing of your data.
*   The right of restriction (to request we restrict processing your data).
*   The right to data portability.
*   The right to withdraw consent at any time.
*(Note: If you have users in the EU/UK or California, you must include specific GDPR and CCPA/CPRA clauses here. Consult a lawyer to ensure full compliance).*

### 6. CHILDREN'S PRIVACY
The App is not intended for use by children under the age of 13 [or 16, depending on your jurisdiction]. We do not knowingly collect personally identifiable information from children. If we become aware that we have collected personal data from a child without verification of parental consent, we will take steps to remove that information.

### 7. THIRD-PARTY LINKS
The App may contain links to other websites or third-party financial data providers. If you click on a third-party link, you will be directed to that site. We have no control over and assume no responsibility for the content, privacy policies, or practices of any third-party sites or services.

### 8. CHANGES TO THIS PRIVACY POLICY
We may update our Privacy Policy from time to time. We will notify you of any changes by posting the new Privacy Policy on this page and updating the "Last Updated" date.

### 9. CONTACT US
If you have any questions about this Privacy Policy, please contact us at: **[Your Email Address]**.

---

### 💡 Implementation Tips for Maximum Protection:

1.  **Clickwrap Agreement:** Don't just put a link in the footer. When a user signs up, force them to check a box that says: *"I have read and agree to the Terms of Service and Privacy Policy. I understand that this app does not provide financial advice."* This is legally much stronger than a "browsewrap" (just having a link at the bottom of the page).
2.  **In-App Disclaimers:** Put a small, persistent disclaimer on the actual dashboard or analysis pages (e.g., a small banner at the top or bottom: *"Data is for informational purposes only. Not financial advice."*).
3.  **Data Minimization:** Since you are dealing with finance-adjacent users, **do not** ask for or store their brokerage passwords, SSN, or bank details unless you are a fully licensed broker-dealer (which you likely aren't). Keep the app strictly to *analysis*.
4.  **Cookie Consent:** If you have users in Europe (GDPR) or California (CCPA), you need a proper Cookie Consent banner that allows them to reject non-essential cookies.

---

## Implementation Analysis: Full 4-Step Signup Flow

### Phased Approach

The full flow is split into two independent phases. **Phase 1** uses Supabase's built-in link-based email confirmation (no custom OTP UI needed). **Phase 2** upgrades to in-page OTP codes and adds Two-Factor Authentication.

| | Phase 1 (Immediate) | Phase 2 (Later) |
|--|---------------------|-----------------|
| Step 1 | Create Account (name, email, password, strength, T&C) | Same |
| Step 2 | **Link-based email verification** — user clicks link in email | **OTP-based** — 6-digit code input in-page |
| Step 3 | Success / onboarding | Two-Factor Auth (TOTP + SMS) + backup codes |
| Step 4 | — | Success / onboarding (with 2FA status) |
| Login | Unchanged | MFA challenge after password |
| Effort | ~3-4 days | ~5-7 days |

### Feasibility

✅ **Phase 1 — Overall** — Feasible, moderate effort
✅ **Phase 2 — Step 2 (Email OTP)** — Feasible, moderate effort
✅ **Phase 2 — Step 3 (Two-Factor Auth)** — Feasible, high effort

### Current State of the Auth System

| Aspect | Current |
|--------|---------|
| Auth backend | **Supabase** (`@supabase/ssr` + `@supabase/supabase-js`) |
| Signup flow | Single step: email + password → `signUpWithEmail()` → redirect to `/dashboard` |
| Form fields | Email + password only (no name, no confirm, no T&C) |
| Email verification | **Not handled** — if Supabase email confirmation is enabled, users get stuck in an error state with no UI |
| 2FA / MFA | **Not implemented** — zero MFA-related code exists |
| Password strength | **Not implemented** — no strength meter or requirements checklist |
| Social OAuth | **Not implemented** — no Google/Apple signup buttons |
| Multi-step form | **Not implemented** — single flat form |
| Backend user profile | Created immediately on signup via `POST /users/sync` — no pending/unverified state exists |

### Supabase API Compatibility

Supabase Auth supports every piece of this flow natively:

| Feature | Supabase API | Status |
|---------|-------------|--------|
| Email + password signup | `supabase.auth.signUp({ email, password })` | Already used in AuthProvider |
| Name in profile | `options: { data: { first_name, last_name } }` in `signUp()` | Passed as `fullName` but ignored by backend |
| Email verification OTP | `supabase.auth.verifyOtp({ email, token, type: 'signup' })` | Available, not used |
| Resend verification | `supabase.auth.resend({ type: 'signup', email })` | Available, not used |
| TOTP MFA enrollment | `supabase.auth.mfa.enroll({ factorType: 'totp' })` | Available, not used |
| TOTP challenge + verify | `mfa.challenge({ factorId })` + `mfa.verify({ factorId, code })` | Available, not used |
| SMS MFA (via Twilio) | Requires Twilio configured in Supabase dashboard + `mfa.enroll({ factorType: 'phone' })` | Available, not used |
| Backup codes | `supabase.auth.mfa.listFactors()` returns enrolled factors; codes generated server-side by Supabase | Available, not used |
| OAuth (Google, Apple) | `supabase.auth.signInWithOAuth({ provider: 'google' })` | Available, not used |

**No new auth backend is needed.** Everything is built into the existing Supabase project (`viqdqgxcumcdhqxooplw`). The only prerequisite is configuration in the Supabase dashboard:
- Email Confirmations: toggle ON (Auth → Settings → General)
- SMS provider (Twilio) configured for phone MFA (Auth → Settings → SMS)
- OAuth providers (Google, Apple) configured (Auth → Providers)

### Detailed Impact Per Step

---

#### Step 1: Create Account

| Current | Target |
|---------|--------|
| Email + password only | First name, last name, email, password, confirm password, password strength meter, requirement checklist, T&C checkbox, social OAuth buttons |

**What was actually implemented:**

| File | Action | Reason |
|------|--------|--------|
| `web/src/components/auth/signup-flow.tsx` | **CREATE** | Parent orchestrator: hosts step progress indicator (left panel on desktop), manages `currentStep` state (1→2→3), handles transitions, `?step=N` query param persistence, session recovery on mount |
| `web/src/components/auth/step-create-account.tsx` | **CREATE** | Step 1: first name, last name, email, password + confirm, password strength meter, requirement checklist, T&C checkbox, Google + Apple OAuth buttons |
| `web/src/components/auth/password-strength.tsx` | **CREATE** | Reusable password strength meter (5 levels: empty/weak/fair/good/strong) |
| `web/src/components/auth/password-requirements.tsx` | **CREATE** | Reusable requirements checklist (12+ chars, upper, lower, number, special, match) |
| `web/src/components/auth/step-verify-email.tsx` | **CREATE** | Step 2: pending verification screen with email display, resend button (60s countdown), auto-poll session every 5s |
| `web/src/components/auth/step-success.tsx` | **CREATE** | Step 3: success state with pop-in animation, signed-in-as display, auto-redirect to /dashboard (5s countdown) |
| `web/src/app/signup/page.tsx` | **MODIFY** | Replace `<SignupForm />` with `<SignupFlow />` wrapped in `<Suspense>` |
| `web/src/components/auth/signup-form.tsx` | **MODIFY** | Cleaned stale Firebase comments; updated `signUpWithEmail` call to match new 4-arg signature |
| `web/src/components/user-nav.tsx` | **MODIFY** | Updated to use new `User` type fields (`first_name`, `last_name`, `avatar_url`) with `getUserDisplayName()` helper |
| `web/src/lib/supabase.ts` | **NO CHANGE** | OAuth providers are called via the existing `supabase.auth.signInWithOAuth()` |
| `web/.env.local` | **MODIFY** | Add OAuth redirect URL if not already configured in Supabase dashboard |

**Validation changes:**
- Add `firstName`, `lastName`, `confirmPassword`, `terms` fields to the Zod schema
- Password minimum: 8 chars → 12 chars (per design doc)
- Real-time password matching between `password` and `confirmPassword`
- T&C checkbox must be `true` for form to be valid

**Dependencies:**
- No new npm packages — `react-hook-form` + `zod` already installed
- No backend changes for name fields — pass as `data: { first_name, last_name }` in Supabase `signUp()` options

---

#### Step 2: Email Verification — Two Implementation Paths

The design doc shows a 6-digit OTP input. Supabase supports two verification modes — Phase 1 uses the simpler link-based approach; Phase 2 upgrades to OTP.

---

##### Phase 1: Link-Based Verification (Faster Path)

| Current | Target |
|---------|--------|
| No verification — user goes directly to dashboard | Pending verification screen: "Check your inbox" with resend link button |

**How it works:** Supabase sends the default confirmation email containing a magic link. The user clicks it, which opens a callback page in the app. The callback uses `supabase.auth.exchangeCodeForSession()` to complete verification. The signup page detects the session change (via `onAuthStateChange`) and advances.

```
signUp() → data.session === null
  → Show pending screen: "We sent a confirmation link to email@example.com"
  → User opens email → clicks "Confirm your mail" link
  → Link opens /auth/callback?code=xxx
  → Callback calls exchangeCodeForSession() → session now active
  → onAuthStateChange fires SIGNED_IN → signup-flow advances to next step
  → persistSessionCookie() → redirect to dashboard (or Step 3 in Phase 2)
```

**No new npm dependencies.** Uses Supabase's built-in `exchangeCodeForSession()`.

**What was actually implemented:**

| File | Action | Reason |
|------|--------|--------|
| `web/src/app/auth/callback/route.ts` | **CREATE** | Route handler: receives `code` query param, calls `supabase.auth.exchangeCodeForSession(code)`, redirects based on provider (OAuth → `/signup?step=3&email=`, email link → `/signup?verified=true&email=`) |
| `web/src/components/auth/step-verify-email.tsx` | **CREATE** | Pending screen: displays user's email, "Check your inbox" message, resend button with 60s countdown (`supabase.auth.resend()`), auto-polls session every 5s |
| `web/src/providers/auth-provider.tsx` | **MODIFY** | On `signUp()`, if `!data.session`, set `status: 'pending_verification'` + `pendingEmail`. Added `signInWithOAuth(provider)`. `onAuthStateChange` reads OAuth metadata (`full_name`, `avatar_url`) |
| `web/src/components/auth/signup-flow.tsx` | **CREATE** | 3-step state machine with `?step=N` persistence. Handles: OAuth redirect (auto-advance to step 3), email verification (step 2), session recovery on refresh |
| `web/src/app/signup/page.tsx` | **MODIFY** | Replaced `<SignupForm />` with `<SignupFlow />`, wrapped in `<Suspense>` for `useSearchParams` |

**Auth flow change (Phase 1):**

```
Current:  signUp() → if !session → throw error ("Sign Up Failed" toast)

Phase 1:  signUp() → if !session → show pending screen
          → user clicks link in email → callback page → session created
          → onAuthStateChange(SIGNED_IN) → advance to Step 3/4
```

**Edge cases:**
- User closes tab before clicking link — session was never persisted, no stale cookie. User can sign in normally (Supabase handles email confirmed state)
- Link expired — Supabase defaults to 24h link expiry; user can request resend
- User is already signed up — Supabase returns `UserAlreadyRegistered` error, handle gracefully

---

##### Phase 2: OTP-Based Verification (Enhanced UX)

| Current | Target |
|---------|--------|
| Link-based (Phase 1) | 6-digit code input with auto-advance, countdown timer, resend button — user never leaves the page |

**Supabase email template change:** The default link template uses `{{ .ConfirmationURL }}`. For OTP, replace it with `{{ .Token }}` in **Supabase Dashboard → Authentication → Email Templates → Confirm signup**.

**What changes additionally for Phase 2:**

| File | Action | Reason |
|------|--------|--------|
| `web/src/components/auth/otp-input.tsx` | **CREATE** | Reusable 6-digit code input (auto-advance, paste support — shared with MFA step) |
| `web/src/components/auth/step-verify-email.tsx` | **MODIFY** | Replace pending screen with OTP code input + timer + resend. Calls `supabase.auth.verifyOtp()` |
| Supabase Dashboard | **MODIFY** | Update email template to use `{{ .Token }}` instead of `{{ .ConfirmationURL }}` |

**OTP flow:**

```
signUp() → data.user.email_confirmed_at == null → show Step 2 OTP input
          → user enters 6-digit code from email
          → verifyOtp({ email, token, type: 'signup' }) → session created
          → onAuthStateChange(SIGNED_IN) → advance to Step 3
```

---

#### Step 3: Two-Factor Authentication (MFA) — Phase 2 Only

| Current | Target |
|---------|--------|
| No 2FA | Method selector (Authenticator App / SMS), QR code display, TOTP code input, SMS phone input, backup codes display + confirmation |

**What changes:**

| File | Action | Reason |
|------|--------|--------|
| `web/src/components/auth/step-two-factor.tsx` | **CREATE** | Parent for Step 3: method selector, toggles between app and SMS sections |
| `web/src/components/auth/mfa-enroll-app.tsx` | **CREATE** | TOTP enrollment: displays QR code from `mfa.enroll()`, 6-digit code input for verification |
| `web/src/components/auth/mfa-enroll-sms.tsx` | **CREATE** | Phone number input, "Send SMS Code" button, 6-digit code input, countdown timer |
| `web/src/components/auth/backup-codes.tsx` | **CREATE** | Displays 8 backup codes after MFA enrollment, "I've saved my codes" confirmation button |
| `web/src/components/auth/signup-flow.tsx` | **MODIFY** | Add Step 3 to the flow + handle enrollment state machine |

**MFA enrollment flow (TOTP):**

```
1. mfa.enroll({ factorType: 'totp' })      → returns { id, totp: { qr_code, secret } }
2. Display QR code to user                  → user scans with authenticator app
3. User enters 6-digit TOTP code
4. mfa.challenge({ factorId: enroll.id })   → returns challenge id
5. mfa.verify({ factorId, challengeId, code }) → returns factor is verified
6. On success: show backup codes
7. User confirms "I've saved my codes"      → advance to Step 4
```

**MFA enrollment flow (SMS):**

```
1. User enters phone number
2. mfa.enroll({ factorType: 'phone', phone: number }) → enrolls phone
3. mfa.challenge({ factorId })                        → sends SMS code
4. User enters 6-digit code
5. mfa.verify({ factorId, challengeId, code })         → factor verified
6. On success: show backup codes
7. User confirms → advance to Step 4
```

**In Phase 1, this entire step is skipped.** After email verification, the user goes directly to the Success screen (Step 4) and is redirected to the dashboard. MFA setup is deferred to Phase 2.

**Backend impact for MFA:**
- On login, the user must complete a second factor challenge. This means:
  - The login form needs MFA-aware logic: detect `mfa.verify()` is required after password
  - `POST /api/auth/session` should NOT be called until MFA is completed
  - `onAuthStateChange` will fire intermediate states — the AuthProvider must handle `MFA_CHALLENGE` events

**Supabase configuration required:**
- Supabase Dashboard → Authentication → Multi-Factor Auth → Enable MFA
- For SMS: Twilio account + configure in Supabase Dashboard → Auth → Settings → SMS Provider

**Dependencies:**
- `qrcode.react` or `qrcode` npm package — for rendering QR code SVG (TOTP enrollment)
- Alternative: render QR code as an `<img>` from a URL like `https://api.qrserver.com/v1/create-qr-code/`

---

#### Step 4: Success / Onboarding

| Phase | Content |
|-------|---------|
| Phase 1 | Simple success screen: "Email verified! Redirecting to dashboard…" with auto-redirect |
| Phase 2 | Rich success: animated checkmark, account details, "2FA enabled" badge, manual "Go to Dashboard" CTA |

**What changes:**

| File | Action | Phase | Reason |
|------|--------|-------|--------|
| `web/src/components/auth/step-success.tsx` | **CREATE** | Both | Success state. Phase 1: simple auto-redirect. Phase 2: full celebration with 2FA status |
| `web/src/components/auth/signup-flow.tsx` | **MODIFY** | Both | Add Step 4: after verification (Phase 1) or MFA enrollment (Phase 2), transition to success, then redirect to `/dashboard` |

**No backend changes needed in either phase.** This step is entirely UI.

---

### Full File Inventory

#### Phase 1 Files to CREATE (✅ All Done)

| File | Purpose |
|------|---------|
| `web/src/components/auth/signup-flow.tsx` | Multi-step orchestrator with step indicator (3 steps), `?step=N` persistence, session recovery |
| `web/src/components/auth/step-create-account.tsx` | Step 1: name fields, email, password + confirm, strength meter, requirements, T&C, Google + Apple OAuth |
| `web/src/components/auth/step-verify-email.tsx` | Step 2: "Check your inbox" pending screen with resend (60s countdown), auto-poll session |
| `web/src/components/auth/step-success.tsx` | Step 3: success animation, signed-in-as display, auto-redirect to /dashboard (5s) |
| `web/src/components/auth/password-strength.tsx` | Password strength bar (5 levels: empty/weak/fair/good/strong) |
| `web/src/components/auth/password-requirements.tsx` | Requirements checklist (12+ chars, upper, lower, number, special, match) |
| `web/src/app/auth/callback/route.ts` | Route handler: exchanges Supabase confirmation code for session; differentiates OAuth vs email link via `provider` metadata |
| `web/src/app/legal/[slug]/page.tsx` | Dynamic server component: reads `public/legal/{slug}.md`, renders as HTML, handles Terms + Privacy |
| `web/public/legal/terms.md` | Terms of Service markdown content |
| `web/public/legal/privacy.md` | Privacy Policy markdown content |
| `backend/api/users.py` | **MODIFIED** (expanded) — `POST /users/sync` (atomic upsert), `GET /users/me`, `PATCH /users/me` |
| `backend/scripts/migrate_users_schema_v2.sql` | SQL migration: `first_name`, `last_name`, `avatar_url` columns + UNIQUE constraints |

**Phase 1 total: 12 files (8 new UI + 1 new API + 1 SQL + 2 modified)**

#### Phase 2 Additional Files to CREATE

| File | Purpose |
|------|---------|
| `web/src/components/auth/otp-input.tsx` | Reusable 6-digit code input (auto-advance, paste — shared with MFA) |
| `web/src/components/auth/step-two-factor.tsx` | Step 3: 2FA method selector + enrollment |
| `web/src/components/auth/mfa-enroll-app.tsx` | TOTP QR + code verification |
| `web/src/components/auth/mfa-enroll-sms.tsx` | SMS phone + code verification |
| `web/src/components/auth/backup-codes.tsx` | Backup codes display + confirmation |

**Phase 2 total: 5 additional new files**

#### Files to MODIFY (Both Phases) — ✅ Phase 1 Done

| File | Phase 1 Change (Done) | Phase 2 Additional Change |
|------|----------------------|--------------------------|
| `web/src/app/signup/page.tsx` | Replace `<SignupForm />` with `<SignupFlow />` (wrapped in `<Suspense>`) | — |
| `web/src/providers/auth-provider.tsx` | Add `pending_verification` status, `signInWithOAuth()`, OAuth metadata reading, 4-arg `signUpWithEmail` | Handle `MFA_CHALLENGE` events |
| `web/src/features/auth/types/auth.types.ts` | Rewrite `User` type to match backend response; add `getUserDisplayName()`, `getUserInitials()` helpers | — |
| `web/src/features/auth/services/auth.service.ts` | `exchangeTokenForUser` sends `first_name`, `last_name`, `avatar_url`; add `fetchCurrentUser()` | — |
| `web/src/components/user-nav.tsx` | Use new `User` fields + helper functions instead of removed `displayName`/`photoURL` | — |
| `web/src/components/auth/signup-form.tsx` | Clean Firebase comments, update `signUpWithEmail` call signature | — |
| `web/src/components/auth/step-verify-email.tsx` | Pending screen with resend only | Upgrade to OTP code input |
| `web/src/components/auth/step-success.tsx` | Reads from auth context, 5s auto-redirect | Full celebration screen with 2FA badge |
| `web/src/components/auth/login-form.tsx` | — | Add MFA challenge step after password |

**Total: 7 files modified in Phase 1, 5 in Phase 2**

#### Files Deleted

| File | Reason |
|------|--------|
| `web/src/app/legal/terms/page.tsx` | Replaced by dynamic `[slug]/page.tsx` |
| `web/src/app/legal/privacy/page.tsx` | Replaced by dynamic `[slug]/page.tsx` |
| `web/src/components/auth/signup-form.tsx` | Replaced by `step-create-account.tsx` + `signup-flow.tsx` |

**3 files deleted.**

---

### Impact on Existing Code

#### AuthProvider (`auth-provider.tsx`) — What Was Implemented

1. ✅ **`pending_verification` status** — `signUpWithEmail()` sets `status: 'pending_verification'` + `pendingEmail` when `!data.session` (instead of throwing an error)
2. ✅ **`signInWithOAuth(provider)`** — calls `supabase.auth.signInWithOAuth()` with `redirectTo: /auth/callback`
3. ✅ **OAuth metadata** — `onAuthStateChange` and `syncWithBackend` read `meta.full_name`, `meta.avatar_url` for Google; `meta.picture` fallback for avatar
4. ✅ **`signUpWithEmail` 4-arg signature** — `(email, password, firstName, lastName)` — names stored via `options.data` in Supabase
5. ✅ **No breaking changes** — old `signup-form.tsx` still works (passes `'', ''` for names)

**Next (Phase 2):** Handle `MFA_CHALLENGE` events in `onAuthStateChange`

#### Login Form (`login-form.tsx`)

When MFA is enrolled for a user, Supabase auth returns `SupabaseAuthMFAError` on password sign-in. The login form must detect this and show a second step: 6-digit TOTP/SMS code input.

**Current:**
```ts
const { data, error } = await supabase.auth.signInWithPassword({ email, password });
if (error) throw error;
// → redirect to dashboard
```

**Target:**
```ts
const { data, error } = await supabase.auth.signInWithPassword({ email, password });
if (error?.code === 'mfa_required') {
  // Show MFA code input → get code from user
  const factors = error.factors; // available factors
  const { data: mfaData, error: mfaError } = await supabase.auth.mfa.challengeAndVerify({
    factorId: factors[0].id,
    code: userEnteredCode,
  });
} else if (error) {
  throw error;
}
// → redirect to dashboard
```

#### Backend (`POST /users/sync`)

**Current:** Expects a fully authenticated user with a valid session. Called from AuthProvider immediately after signup.

**Impact:**
- If email verification is added, the backend user profile should NOT be created until email is confirmed
- The `/users/sync` endpoint should either:
  - Accept an `unverified` status field and skip certain features until verified
  - OR only be called after email + MFA are both complete
- **Recommended approach:** Keep calling `/users/sync` on signup but add a `status: "pending_verification"` field. The backend can choose to restrict access until the user is fully verified. This avoids a breaking change.

**Backend changes needed:**
- `POST /users/sync` — add optional `status` field in request body; create user with `pending` status
- All authenticated endpoints — optionally check user status before serving data; return 403 with `ACCOUNT_PENDING_VERIFICATION` if not yet verified

Without backend changes, the workaround is: call `/users/sync` only after the entire 4-step flow is complete (Step 4). This has the risk of data loss if the user abandons mid-flow.

---

### Dependency Changes

| Package | Version | Size | Required For |
|---------|---------|------|-------------|
| `qrcode.react` | latest | ~15KB | Render TOTP QR code as SVG in Step 3 |
| OR: `qrcode` | latest | ~25KB | Generate QR code as data URL, render as `<img>` |
| **No other new npm packages** | — | — | Everything else uses existing Supabase SDK |

`react-hook-form` + `zod` are already installed for form validation.
`clsx`/`tailwind-merge`/`class-variance-authority` are already installed for styling.

---

### This analysis updates the following stale references discovered during codebase exploration:

| Location | Stale Reference | Correction |
|----------|----------------|------------|
| `signup-form.tsx:74-79` | Comments reference Firebase APIs (`createUserWithEmailAndPassword`, `setAuthToken`, `exchangeTokenForUser`) | App uses **Supabase**, not Firebase. Comments should be cleaned up. |

---

### Migration Steps (Ordered)

**Phase 1 (✅ IMPLEMENTED)**

```
  ── Backend & Schema ── (✅ All Done)
 1. ✅ ALTER TABLE users ADD COLUMN first_name TEXT, last_name TEXT, avatar_url TEXT
    → backend/scripts/migrate_users_schema_v2.sql (executed on Supabase)
 2. ✅ Update POST /users/sync to accept + store first_name, last_name, avatar_url
    → backend/api/users.py — uses atomic .upsert() with UNIQUE constraints
 3. ✅ Create GET /users/me endpoint (read profile without writing)
    → backend/api/users.py — read-only, no last_signed_in update
 4. ✅ (Optional) Create PATCH /users/me endpoint for profile editing
    → backend/api/users.py

  ── Frontend Auth Infra ── (✅ All Done)
 5. ✅ Update frontend User type + mapping to match backend response
    → web/src/features/auth/types/auth.types.ts — user_id, auth_id, email, username,
      first_name, last_name, avatar_url, preferred_currency, last_signed_in
 6. ✅ Create auth/callback/route.ts (handles OAuth & email verification redirects)
    → Passes ?email= param to signup page for pre-fill
 7. ✅ Update auth-provider.tsx: add pending_verification status, handle !session
    → signUpWithEmail now accepts (email, password, firstName, lastName)
 8. ✅ Update exchangeTokenForUser to read OAuth metadata (full_name, avatar_url)
    → Reads meta.full_name + meta.avatar_url for Google; meta.picture fallback

  ── UI Components ── (✅ All Done)
 9. ✅ Create password-strength.tsx, password-requirements.tsx
    → web/src/components/auth/password-strength.tsx (5 levels: empty/weak/fair/good/strong)
    → web/src/components/auth/password-requirements.tsx (6-rule checklist)
10. ✅ Create signup-flow.tsx with step indicator + state machine (3 steps)
    → web/src/components/auth/signup-flow.tsx — ?step=N persistence, session recovery
11. ✅ Create step-create-account.tsx with name fields, social OAuth buttons,
    strength meter, T&C checkbox
    → web/src/components/auth/step-create-account.tsx — Google + Apple OAuth
12. ✅ Create step-verify-email.tsx (Phase 1: pending screen + resend button)
    → web/src/components/auth/step-verify-email.tsx — 60s countdown, auto-poll
13. ✅ Create step-success.tsx (Phase 1: auto-redirect to /dashboard in 5s)
    → web/src/components/auth/step-success.tsx — reads email from auth context
14. ✅ Update signup/page.tsx to use SignupFlow
    → Wrapped in <Suspense> for useSearchParams

  ── Legal Pages ── (✅ All Done)
15. ✅ Dynamic /legal/[slug] route reading from public/legal/*.md
    → web/src/app/legal/[slug]/page.tsx — server component, fs.readFileSync
    → web/public/legal/terms.md, web/public/legal/privacy.md
    → No dependencies — custom markdown renderer handles headings, bold, lists, links

  ── Cleanup ── (✅ Done)
16. ✅ Correct stale Firebase comments in signup-form.tsx

  ── data-testid Attributes ── (✅ Done)
17. ✅ Added to: google-oauth-btn, apple-oauth-btn, first-name-input, last-name-input,
    email-input, password-input, confirm-password-input, terms-checkbox,
    create-account-submit, resend-btn, email-signup-form

  ── Tests ── (⚠️ NOT YET WRITTEN)
18. ❌ Unit tests: password-strength, password-requirements, step-create-account,
    step-verify-email, step-success
19. ❌ Integration tests: email signup happy path, OAuth happy path (mock),
    validation failure, step navigation, email-already-exists
```

**Phase 2 — OTP Email + Two-Factor Auth (later, independent)**

19. Create `otp-input.tsx`: reusable 6-digit code input with auto-advance
20. Update `step-verify-email.tsx`: replace pending screen with OTP code input + `verifyOtp()` call
21. Update Supabase email template: change `{{ .ConfirmationURL }}` → `{{ .Token }}`
22. Enable MFA in Supabase Dashboard (requires Team/Pro plan)
23. Create `mfa-enroll-app.tsx`, `mfa-enroll-sms.tsx`, `backup-codes.tsx`
24. Create `step-two-factor.tsx` with method selector
25. Create `step-success.tsx` (Phase 2): full celebration screen with 2FA badge
26. Update `login-form.tsx`: handle `mfa_required` error with MFA challenge code input
27. Wire all steps in `signup-flow.tsx`: 4-step flow (Create → Verify OTP → MFA → Success)

**Phase 3 — Production Hardening (applies to either phase)**
28. E2E tests: full email signup, social OAuth, session expiry, popup blocker, mobile responsive, keyboard-only
29. Add social OAuth buttons (Google, Apple) in Step 1 — including popup-blocker fallback to redirect
30. Animations: step transitions, success pop-in, shake on error, staggered field entrance
31. Mobile responsive: hide left panel, full-width steps
32. Accessibility: ARIA labels, focus management, screen reader announcements, keyboard navigation, touch targets
22. Accessibility: ARIA labels, focus management, screen reader announcements, keyboard navigation, touch targets
23. Add `data-testid` attributes to all interactive elements for test automation

---

### Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Auth flow regression** (existing users can't sign in) | Low | **Critical** | Phase 1 is purely additive; old `signup-form.tsx` remains working until the new `signup-flow.tsx` replaces it in step 9 of the migration. Login form changes are Phase 2 only |
| **Supabase MFA not enabled on the project** | High | **Blocking for Phase 2** | Must be enabled in Supabase Dashboard before Phase 2 MFA can proceed. Verify Supabase plan supports MFA (requires Team/Pro plan). Phase 1 does NOT require MFA |
| **Twilio not configured** | High | **Blocks SMS MFA** | SMS option can be omitted if Twilio is not set up; TOTP-only MFA is still feasible |
| **Backend `/users/sync` doesn't accept pending status** | Medium | **Medium** | Defer `/users/sync` call until after Step 4; risk of abandoned-user data loss, mitigated by Supabase still having the auth record |
| **Email already enabled in Supabase** | Medium | **Low** | If email confirmation is already on, new signups are already stuck in an error state. Phase 1 fixes this — becomes a bugfix, not a regression |
| **State machine complexity** (user refreshes mid-flow) | Medium | **Medium** | URL search params (`?step=N`) persist step across refresh. Session recovery logic on mount (see Mid-Flow Refresh section). Form data preserved in sessionStorage |
| **OAuth popup blocked** | Medium | **Low** | Auto-detect blocked popup via `window.open` null check → fallback to redirect mode (see OAuth Error Recovery section) |
| **OAuth provider returns error** | Low | **Low** | Error shown inline with retry button; user can switch to email/password (see Error Recovery table) |
| **Accessibility non-compliance** | Medium | **Medium** | WCAG AA contrast, focus management, ARIA labels, keyboard nav all specified in Accessibility section |
| **E2E test flakiness** (OAuth round-trip) | Medium | **Low** | Use `playwright-mock-oauth` or test Google account; test `exchangeCodeForSession` mock in integration tests |
| **Existing unit tests for signup** | None exist | **Zero** | No existing signup tests to break |
| **Bundle size increase** | Low | **Low** | 11 new components, all on the signup page which is not part of the authenticated app bundle. Zero impact on dashboard/analysis performance |

---

### Mid-Flow Refresh & Session Recovery

A user can lose their session mid-flow (browser crash, tab close, cookie expiry). The design must handle this without data loss or forcing a restart.

#### Recovery Strategy by Step

| Step | On Page Load | What Happens | Recovery Mechanism |
|------|-------------|--------------|-------------------|
| Step 1 (Create Account) | `?step=1` or no param | No session exists | Show Step 1 normally — nothing to restore |
| Step 2 (Verify Email) | `?step=2`, no session | User hasn't confirmed email yet | Redirect to Step 1 with toast: *"Session expired. Please sign up again."* |
| Step 2 (Verify Email) | `?step=2`, has session (`email_confirmed_at` is null) | User confirmed email but `onAuthStateChange` hasn't fired yet | Show Step 2 normally; re-poll session every 5s |
| Step 2 (Verify Email) | `?step=2`, has session + `email_confirmed_at` is set | Already verified | Auto-advance to Step 4 (Phase 1) or Step 3 (Phase 2) |
| Step 3/4 (MFA/Success, Phase 2) | `?step=3` or `?step=4`, has session | User is fully authenticated | Redirect to dashboard — user already completed flow |
| OAuth callback | `/auth/callback?code=xxx`, no session yet | OAuth code ready to exchange | Exchange code as normal; on success redirect to `/signup?step=3` |

#### Implementation

```ts
// signup-flow.tsx — on mount recovery logic
const step = searchParams.get('step')
const session = await supabase.auth.getSession()

if (step === '2' || step === '3') {
  if (!session.data.session) {
    // Session expired mid-flow — redirect to Step 1
    router.replace('/signup')
    toast.error('Session expired. Please sign up again.')
    return
  }
  if (session.data.session.user.email_confirmed_at) {
    // Already verified — skip ahead
    goToStep(Phase1 ? 4 : 3)  // Phase 1 → success; Phase 2 → MFA
  }
}
```

#### Step Persistence

| Approach | Used For | Rationale |
|----------|----------|-----------|
| `?step=N` query param | **Primary** | Survives refresh, bookmarkable, shareable. Single source of truth |
| `sessionStorage` | **Secondary** | Stores form data (name, email) to pre-fill if user goes back |
| `session` | **Auth state** | Supabase session tells us if user is verified, OAuth-linked, etc. |

Form data (first name, last name) is saved to `sessionStorage` on each `onChange` and cleared on flow completion. This lets the user recover their partially-filled form if they navigate away and come back within the same browser session.

**Do NOT use** `localStorage` for form data — it persists across sessions and would show stale data.

#### Session Refresh During Flow

The auth-provider already refreshes the session cookie every 45 minutes via `setInterval`. During the signup flow, this interval is active but the user is unlikely to spend 45 minutes on Step 2. If the session does expire mid-flow (user leaves the tab open), the `onAuthStateChange` handler fires `SIGNED_OUT`, which resets state. The `?step` query param ensures they land back on the right step after re-authenticating.

---

### OAuth Error Recovery

OAuth flows are inherently fragile — popups can be blocked, users can cancel mid-flow, and providers can return errors. The design must handle every failure mode gracefully.

#### Failure Modes and Handling

| Failure Mode | When It Happens | Root Cause | UX Handling |
|-------------|----------------|------------|-------------|
| **Popup blocked** | `signInWithOAuth()` is called | Browser blocked the popup | Show inline error: *"Popup was blocked. Please allow popups for this site or use email signup."* + a "Try Again" button that opens in same window using `redirectTo` instead of popup |
| **User cancelled** | User closes the OAuth popup/tab | User changed their mind | Detect via `visibilitychange` or `window.closed` polling. Show Step 1 as-is with no error — user is back where they started |
| **Provider error** | Google returns `access_denied` | User denied specific scopes | Show alert: *"Google signup failed. You can try again or use email & password."* Log the error but don't expose raw error to user |
| **Email already exists** | OAuth returns an email linked to an existing password account | Same email, different method | Supabase returns `email_link_identity_exists` or similar. Show: *"This email is already registered. Sign in with your password or try a different method."* |
| **Network failure** | After redirect, `/auth/callback` can't reach Supabase | User lost connectivity | Show retry screen with button: *"Connection lost. [Try Again]"* — re-triggers `exchangeCodeForSession()` |
| **Account linking conflict** | Google account linked to email that already has a different Google account | Rare | Show: *"This Google account is already linked to another user. Please sign in with the existing account."* |

#### Redirect vs Popup

Two `signInWithOAuth` modes exist:

| Mode | Pros | Cons | Used When |
|------|------|------|-----------|
| **Redirect** (`redirectTo`) | No popup blocker issues, works on mobile | Full page redirect away from app; user leaves signup flow | **Primary** for mobile and as popup fallback |
| **Popup** (default) | User stays on signup page; seamless UX | Blocked by ~30% of browsers; no mobile support | **Primary** on desktop with popup blocker detection |

**Strategy:**
```
Desktop (screen width > 768px):
  1. Try popup first
  2. On `window.opener === null` detection → switch to redirect
Mobile (screen width ≤ 768px):
  Use redirect directly (no popup attempt)
```

#### Popup Blocker Detection

```ts
const popup = window.open('', '_blank', 'width=500,height=600')
if (!popup || popup.closed || typeof popup.closed === 'undefined') {
  // Popup blocked — fall back to redirect
  await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: { redirectTo: `${origin}/auth/callback` }
  })
}
```

#### OAuth Callback Route Differentiation

The same `/auth/callback` route handles both email verification and OAuth redirects. It differentiates by checking the `provider_token` or `type` parameter:

```ts
// auth/callback/route.ts
const { data, error } = await supabase.auth.exchangeCodeForSession(code)

if (error) {
  // OAuth failure or stale code
  redirect('/signup?error=oauth_failed')
}

const isOAuth = data.session?.user?.app_metadata?.provider !== 'email'
// isOAuth = true for Google/Apple, false for email confirmation link

if (isOAuth && data.session?.user?.email_confirmed_at) {
  redirect('/signup?step=3')  // Skip email verification
} else {
  redirect('/signup?verified=true')  // Email confirmation link — advance to Step 2/4
}
```

---

### Accessibility (a11y)

The multi-step signup form is the most interaction-heavy page in the app. It must be usable by keyboard-only users, screen reader users, and users with motor impairments.

#### ARIA Landmarks

```tsx
<main role="main" aria-label="Sign up, step {currentStep} of {totalSteps}">
  <nav aria-label="Progress" role="progressbar" aria-valuenow={currentStep} aria-valuemin={1} aria-valuemax={totalSteps}>
    {/* Step indicator */}
  </nav>
  <section aria-label={stepLabels[currentStep]} role="form">
    {/* Step content */}
  </section>
</main>
```

#### Focus Management

| Trigger | Focus Target | Implementation |
|---------|-------------|----------------|
| Step advances | First focusable element in new step | `useEffect` → `ref.current?.focus()` on the new step container's first input |
| Step goes back | "Back" button or previous step's last field | Same pattern — focus on back button |
| Error appears | First error message | `role="alert"` on error container, `useEffect` calls `focus()` |
| Field validation error | The invalid field | `ref` on each input, call `fieldRef.current?.focus()` on validation failure |
| OAuth popup returns | Step 3 or success screen | Focus the first actionable element (continue button) |
| Timer expires (resend available) | Resend button | `ref` on resend button, focus after timer reaches 0 |

**Animation consideration:** When using `fadeSlideIn` (300-400ms), focus should be moved **after** the animation completes to ensure the element is rendered and positioned:

```tsx
useEffect(() => {
  if (isActive) {
    const timer = setTimeout(() => firstFieldRef.current?.focus(), 400)
    return () => clearTimeout(timer)
  }
}, [isActive])
```

#### Keyboard Navigation

| Key | Action | Scope |
|-----|--------|-------|
| `Tab` | Next field / control | Standard form behavior |
| `Shift+Tab` | Previous field / control | Standard form behavior |
| `Enter` | Submit current step | On any input inside the form |
| `Escape` | Close alert / dismiss error | Error banners only |
| `←` / `→` | Step back / forward (when focus is on step indicator) | Step indicator nav buttons |
| `Ctrl+Shift+Period` | Show password toggle | On any password field |
| `Space` | Toggle checkbox / T&C | Keyboard accessibility |

**No custom keyboard shortcuts override browser defaults.** The `←`/`→` navigation only works when focus is explicitly on the step indicator to prevent interfering with text navigation.

#### Screen Reader Announcements

| Event | Announcement | Technique |
|-------|-------------|-----------|
| Step changes | `"Step {N} of {M}: {step title}"` | `aria-live="polite"` region on step indicator |
| Error appears | `"{error message}"` | `role="alert"` on error container |
| Password strength changes | `"Password strength: {label}"` | `aria-describedby` on password input pointing to strength label |
| Timer countdown | Automatically announced every 15s | `aria-live="polite"` on timer element, update only at 45s, 30s, 15s, resend-ready intervals |
| OAuth in progress | `"Opening Google sign in. Stay on this page while we redirect you."` | `aria-live="assertive"` before redirect; cleared on return |
| Code input (OTP) | `"Digit {N} of 6"` on each input focus | `aria-label` per digit input |

#### Color and Contrast

| Element | Contrast Ratio | Against |
|---------|---------------|---------|
| Form labels (`#94a3b8`) | 4.6:1 | `#0f172a` background ✅ |
| Error text (`#fca5a5`) | 7.1:1 | `rgba(239,68,68,0.1)` background ✅ |
| Placeholder text (`#475569`) | 3.2:1 | `#0f172a` background ⚠️ Below 4.5:1 recommended for WCAG AA. Change to `#64748b` (4.8:1) |
| Accent text (`#818cf8`) | 6.9:1 | `#0f172a` background ✅ |
| Muted text (`#64748b`) | 4.8:1 | `#0f172a` background ✅ |

**Fix:** Change `--text-subtle` placeholder color from `#475569` to `#64748b` for WCAG AA compliance.

#### Touch Targets

| Element | Current Size | Minimum | Status |
|---------|-------------|---------|--------|
| Password toggle button | ~30×30px | 44×44px | ❌ Increase padding to 10px min on all sides |
| Social OAuth buttons | ~50×42px | 44×44px | ✅ (row height) |
| Code digit inputs | 52×60px | 44×44px | ✅ |
| Method option cards | Full width × ~72px | 44×44px | ✅ |
| Resend button | ~130×42px | 44×44px | ✅ |
| Back link | Text link | 44×44px click area | ❌ Increase click area: padding or `::before` pseudo-element |

---

### Test Strategy

The signup flow involves a redirect round-trip, external OAuth popup, and multi-step client state. Unit tests alone cannot cover this — a three-layer approach is needed.

#### Layer 1: Unit Tests (Component-Level)

| Component | What to Test | File |
|-----------|-------------|------|
| `password-strength.tsx` | Renders correct bar width for each strength level (empty/weak/fair/good/strong). Displays correct label text. Updates in real-time as password changes | `password-strength.test.tsx` |
| `password-requirements.tsx` | Shows unmet requirements with grey dots, met requirements with green checkmarks. Tracks all 6 rules (length, upper, lower, number, special, match) | `password-requirements.test.tsx` |
| `otp-input.tsx` | Each input accepts exactly 1 digit. Auto-advances focus to next input on entry. Supports paste (6 digits at once). Backspace goes to previous input. `onComplete` fires when all 6 digits filled | `otp-input.test.tsx` |
| `step-create-account.tsx` | Renders all fields + social buttons. Validates required fields on submit. Shows validation errors. Calls `onStepComplete` with form data on valid submit. T&C checkbox must be checked | `step-create-account.test.tsx` |
| `step-verify-email.tsx` (Phase 1) | Shows pending message with email. Resend button disabled during countdown. Resend button enabled after countdown. Displays error on failed resend | `step-verify-email.test.tsx` |
| `step-success.tsx` | Shows success icon and email. "Go to Dashboard" button renders. Auto-redirect timer fires after N seconds | `step-success.test.tsx` |
| `mfa-enroll-app.tsx` (Phase 2) | Displays QR code. Code inputs render and accept input. Calls `verify()` with code. Shows error on mismatch | `mfa-enroll-app.test.tsx` |

**Testing approach for forms:**
- Wrap each step component with `TestProvider` (mock auth context)
- Use `userEvent` for realistic interactions (type, click, tab)
- Mock Supabase calls at the edge (`signUp`, `signInWithOAuth`, `resend`, `verifyOtp`, `mfa.*`)

#### Layer 2: Integration Tests (Flow-Level)

| Test | What It Validates | Mocking |
|------|-------------------|---------|
| Email signup happy path | Step 1 submit → Step 2 shows (pending) → mock email confirmation → callback route → Step 3/4 shows | Mock Supabase calls: `signUp` returns `{data: {user}, error: null, session: null}`, `exchangeCodeForSession` returns valid session |
| Social OAuth happy path | Click Google button → popup opens → after redirect → callback route → Step 3 shows (skip email verification) | Mock `signInWithOAuth` returns redirect URL. Mock callback route exchanges code |
| Validation failure | Submit empty form → errors shown. Submit weak password → strength bar + requirements feedback. Submit mismatched passwords → "passwords match" requirement fails | No Supabase mocking needed (pure client-side) |
| Step navigation | Clicking step indicator items (if allowed). Browser back/forward with `?step` param. Page refresh at each `?step` value | Mock Supabase session state per test |
| Email already exists | Signup with existing email → error "email already registered" shown | Mock `signUp` throws error with Supabase `"user_already_exists"` message |

#### Layer 3: E2E Tests (Playwright/Cypress)

| Test | Setup | What It Validates |
|------|-------|-------------------|
| Full email signup | Create a test user in Supabase; use `test@example.com` with a test email service (MailSlurper, Ethereal) | User completes all steps; lands on dashboard; profile page shows name and email |
| Social OAuth | Use a test Google account or mock the OAuth provider with `supabase-community/supabase-oauth-test-helper` | OAuth button click → redirect → callback → account created → skip email verification |
| Session expiry mid-flow | Set short session expiry; start signup; wait for expiry; refresh | User redirected to Step 1 with "session expired" message; form data preserved in sessionStorage |
| Popup blocker | Mock `window.open` to return `null` | Fallback to redirect mode; flow completes via redirect |
| Mobile responsive | Set viewport to 375×812 | Left panel hidden; form is full-width; step indicator is compact (horizontal dots or dropdown) |
| Keyboard-only | No mouse interactions | All steps navigable with Tab + Enter; no focus traps; error announcements read by screen reader |

**E2E Tooling Recommendation:** Playwright (already commonly used with Next.js). Key configuration:

```ts
// playwright.config.ts
export default defineConfig({
  testDir: './e2e',
  use: {
    baseURL: 'http://localhost:3000',
    testIdAttribute: 'data-testid',  // add data-testid to key elements
  },
})
```

**Add `data-testid` attributes to all interactive elements:**
```tsx
<button data-testid="google-oauth-btn" ... />
<input data-testid="first-name-input" ... />
<div data-testid="step-indicator" ... />
```

#### What to Skip Testing

| Area | Reason |
|------|--------|
| Supabase Auth internals | Supabase is a third-party service; test our integration, not their correctness |
| Backend `POST /users/sync` | Already covered by 36 existing analysis tests' auth setup; no changes to this endpoint |
| T&C / Privacy Policy content | Legal document; test the checkbox requirement, not the text |
| Password strength algorithm | Pure function; test via unit test on the `calculateStrength()` helper |
| MFA challenge timing | Supabase manages TOTP timing; test that our UI calls `mfa.verify()` correctly |

#### Test Data Strategy

| Data | Source | Notes |
|------|--------|-------|
| Test email | `test-{uuid}@opencode-test.stockerpro.local` | Unique per test run; uses MailSlurper for catching |
| Test OAuth | Google test account or `playwright-mock-oauth` plugin | Pre-configured in Supabase test project |
| Test passwords | `TestPass-{uuid}!` | Meets all 6 requirements; unique per run to avoid Supabase rate limits |
| Rate-limited tests | Use `test.describe.serial` for sequential email resend tests | Avoid 429 errors from Supabase |

---

### Summary

#### Phase 1 (Link-Based Email Verification, no MFA)

| Step | Status | Backend Impact | Frontend Files |
|------|--------|---------------|----------------|
| 1. Backend schema + endpoints | ✅ Done | `migrate_users_schema_v2.sql`, `users.py` (3 endpoints) | — |
| 2. Auth infra (User type, callback, provider, service) | ✅ Done | — | 4 files changed |
| 3. UI components (1-2-3 step flow) | ✅ Done | — | 8 files (6 new, 2 modified) |
| 4. Legal pages (file-based markdown) | ✅ Done | — | 3 files (page + 2 .md) |
| 5. Cleanup | ✅ Done | — | 1 file modified |
| 6. data-testid attributes | ✅ Done | — | Added to key elements |
| 7. Unit + integration tests | ❌ Not written | — | 0 files |
| **Total Phase 1** | **~88% Done** | **3 files** | **~16 files changed** |

#### Phase 2 (OTP Email + Two-Factor Auth)

| Step | Feasibility | Est. Effort | Backend Impact | New Files | Deps Added |
|------|------------|-------------|---------------|-----------|------------|
| Upgrade Step 2 to OTP | ✅ Feasible | 1 day | None | 1 | None |
| 3. Two-Factor Auth | ✅ Feasible | 3-5 days | None for TOTP; SMS needs Twilio | 4 | `qrcode.react` |
| 4. Success (enhanced) | ✅ Feasible | 0.5 day | None | — | — |
| Login MFA support | ✅ Feasible | 1-2 days | None (all Supabase-side) | 0 | None |
| **Total Phase 2** | — | **~6-8 days** | **None** | **5 files** | **`qrcode.react`** |

**Backend pending status:** ⚠️ Optional — only needed if restricting features for unverified users (0.5-1 day). Default workaround: call `/users/sync` after all steps complete.

---

### Backend & Supabase Schema Impact

#### Verified Against: The Current Backend

The analysis above was verified by reading every file in the backend that touches users. Here's what was checked:

| File | What it does |
|------|-------------|
| `backend/api/users.py` | `POST /users/sync` — upserts user record into `users` table |
| `backend/auth.py` | JWT verification via `get_current_user` dependency |
| `backend/database.py` | Supabase client initialization |
| `backend/infrastructure/repositories/supabase_repository.py` | `SupabaseUserRepository.find_by_firebase_uid()` |
| `backend/domain/interfaces/repository.py` | `UserRepository` ABC |
| `backend/main.py` | Router mounting, middleware registration |
| `backend/dependencies.py` | DI wiring, `get_current_user_dep` |

#### Conclusion: Zero Backend Changes Required

**For Phase 1 (link-based email verification):**

The `POST /users/sync` endpoint (called by `exchangeTokenForUser()` on the frontend) is only invoked inside `onAuthStateChange(SIGNED_IN)` after a valid session exists. The Phase 1 flow ensures:

```
signUp() → !session → pending_verification state
  → user clicks confirmation link in email
  → /auth/callback route exchanges code for session
  → onAuthStateChange(SIGNED_IN) fires
  → persistSessionCookie() + exchangeTokenForUser() called
  → POST /users/sync hits backend with a valid JWT
```

By the time the backend receives the request, Supabase Auth has already verified the user's email and issued a valid JWT. The backend's `get_current_user` dependency validates the JWT cryptographically — it does not and does not need to check any `status` or `verified` field.

**For Phase 2 (OTP email + MFA):**

Supabase MFA is handled entirely server-side by Supabase Auth. A full JWT session is only issued after the MFA challenge (TOTP or SMS) completes successfully. The backend never sees a partially-authenticated user. Same JWT validation, same endpoint, zero changes.

#### The `users` Table Schema

The `users` table is a lightweight local mirror of Supabase Auth users. It has exactly these columns (inferred from code usage):

| Column | Type | Written by |
|--------|------|-----------|
| `user_id` | integer (PK, auto-increment) | Supabase |
| `auth_id` | text (Supabase Auth UID) | `POST /users/sync` |
| `email` | text | `POST /users/sync` |
| `username` | text | `POST /users/sync` |
| `last_signed_in` | timestamptz | `POST /users/sync` |
| `preferred_currency` | text (default: 'USD') | `POST /users/sync` |

**No `status`, `verified`, `is_active`, or `is_enabled` column exists.** None is needed because:
- **Email verification** is managed entirely by Supabase Auth (it gates JWT issuance)
- **MFA status** is managed entirely by Supabase Auth (it gates JWT issuance)
- The backend trusts Supabase JWTs — if the JWT is valid, the user is fully authenticated

#### Optional Hardening (Defense-in-Depth)

If you want the backend to explicitly track and enforce verification state (independent of Supabase Auth), you can add a `status` column:

```sql
ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
```

Then update `POST /users/sync` to accept and write a `status` field, and add a check in the `get_current_user` dependency to reject non-`active` users. This would require:

| File | Change |
|------|--------|
| `backend/api/users.py` | Accept optional `status` field in `UserSync` schema; include it in the upsert payload |
| `backend/auth.py` | After JWT validation, look up user by `auth_id` and reject if `status != 'active'` |
| Supabase Dashboard | Run the ALTER TABLE migration above |

**This is optional and not required for either Phase 1 or Phase 2.** It provides defense-in-depth but adds complexity with no immediate benefit since Supabase Auth already enforces verification.

---

### Social OAuth (Google / Apple) — Full Analysis

The design doc mentions social OAuth buttons in Step 1 (items 2290, 2305, 2661) but did **not** fully analyze the backend flow, redirect handling, or UX implications. Here is that analysis.

#### How Supabase OAuth Works

```
User clicks "Sign in with Google"
  → supabase.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: '...' } })
  → Browser redirects to Google consent screen
  → User consents → Google redirects to Supabase
  → Supabase processes callback → redirects to the app's redirectTo URL
  → App callback page loads → Supabase stores session in localStorage
  → onAuthStateChange fires with 'SIGNED_IN' event
  → AuthProvider calls exchangeTokenForUser → POST /users/sync
```

#### Gap 1: No Callback Route Exists

There is **no route handler** at `web/src/app/auth/callback/route.ts` or `web/src/app/auth/callback/page.tsx`. The app currently works without one because the current flow (email/password) gets the session back synchronously from `signUp()`. But OAuth requires a redirect round-trip — the callback page must:
1. Call `supabase.auth.exchangeCodeForSession(code)` (or rely on `onAuthStateChange` auto-detecting the session)
2. Route the user to the app (or the multi-step flow)

Without this, OAuth sign-in would fail at the redirect step.

#### Gap 2: Backend Doesn't Capture OAuth Metadata

Google returns `user_metadata.full_name` and `user_metadata.avatar_url` in the Supabase session, but the backend:

| Data | Google Provides | Backend stores | Problem |
|------|---------------|----------------|---------|
| Email | `session.user.email` | `email` | ✅ Works |
| Name | `session.user.user_metadata.full_name` | ❌ Not captured | `users` table has no name column |
| Avatar | `session.user.user_metadata.avatar_url` | ❌ Not captured | `users` table has no `avatar_url` column |
| Display name | `user_metadata.full_name` | `username` column | Stores email as fallback, but not displayed |

#### Gap 3: OAuth User Has No Name on Profile

Currently `exchangeTokenForUser` sends:
```ts
// auth.service.ts:17
username: params.displayName || params.email  // displayName is null for OAuth → becomes email
```

Since `displayName` comes from `session.user.user_metadata?.display_name` and Google uses `full_name` (not `display_name`), the `displayName` is always `null` for OAuth users. The `username` stored in the DB is the email address.

#### Gap 4: UX — Do OAuth Users Skip Steps?

If a user signs up via Google:
- Email is **already verified** by Google (Supabase sets `email_confirmed_at` automatically)
- No password exists — they authenticate via Google OAuth tokens
- They have **no TOTP MFA enrolled** (would need a separate MFA step)

The multi-step flow must handle this:

| Step | Email/Password User | Google OAuth User |
|------|-------------------|-------------------|
| Step 1: Create Account | Fills form + checks T&C | Clicks "Sign in with Google" → redirected away |
| Step 2: Verify Email | Must enter OTP code from email | ✅ **Auto-completed** (Google verified the email) |
| Step 3: Set Preferences | Selects currency, notification prefs | Same — needs a preferences step |
| Step 4: Confirm & Finish | Reviews + accepts | Same |

**Recommendation**: On return from OAuth redirect, detect that `session.user.email_confirmed_at` is set and auto-advance past Step 2. Show a brief "Verification complete ✓" transition animation (300ms) then proceed to Step 3.

#### Gap 5: Backend UserSync Schema Accepts OAuth Data

Reviewing `UserSync` (backend):
```py
class UserSync(BaseModel):
    email: str
    username: str
```

The existing schema accepts `email` and `username`. Since the frontend sends `username: displayName || email`, OAuth users will have `username` set to their email (no crash). Once we add `first_name`/`last_name` columns, we need the backend to also accept a `display_name` (or `full_name`) field and write it to a new column.

#### What Must Change for OAuth to Work

| # | Change | File(s) |
|---|--------|---------|
| 1 | **Create auth callback route** – `auth/callback/route.ts` to handle OAuth redirects | `web/src/app/auth/callback/route.ts` |
| 2 | **Add OAuth button to Step 1** – Google + Apple buttons next to email form | `web/src/components/auth/step-create-account.tsx` |
| 3 | **Add `display_name` column to `users` table** (or reuse `first_name`/`last_name`) | Supabase Dashboard (ALTER TABLE) |
| 4 | **Update `UserSync` schema** to accept `display_name` field | `backend/api/users.py` |
| 5 | **Update `exchangeTokenForUser`** to read OAuth metadata — use `session.user.user_metadata.full_name` for Google, or `session.user.user_metadata.name` (generic) | `web/src/features/auth/services/auth.service.ts` |
| 6 | **Update `onAuthStateChange` handler** to pass correct metadata for OAuth users | `web/src/providers/auth-provider.tsx` (line 182) |
| 7 | **Supabase Dashboard** – enable Google + Apple as OAuth providers, configure client ID/secret + redirect URL | Supabase Dashboard (Auth → Providers) |
| 8 | **`.env.local`** – add OAuth `redirectTo` URL if not in Supabase dashboard config | `.env.local` |

#### UX Flow: Combining OAuth with Multi-Step

```
User arrives at /signup
  ├── Fills email/password form → Step 2 (verify email via OTP)
  └── Clicks "Sign in with Google"
        → Redirected to Google → consents → back to /auth/callback
        → Session detected → redirect to /signup?step=3 (skip Step 2)
        → Step 3: Preferences pre-filled from Google metadata
        → Step 4: Confirm
```

The `SignupFlow` state machine must accept a `?step` query param to resume at the correct step after OAuth redirect. Since the session persists across redirects, Step 3 can call `syncWithBackend()` to upsert the profile with whatever data Google provided.

#### Edge Cases

| Scenario | Handling |
|----------|----------|
| User signs up via Google, then later clicks "Forgot password" | Supabase supports `supabase.auth.resetPasswordForEmail()` for OAuth-linked emails |
| User signs up via Google, then wants to add email/password | Supabase supports `supabase.auth.updateUser({ password })` to set a password for an OAuth identity |
| Same email, different provider (e.g., Google then Apple) | `POST /users/sync` links by email (Case 2: existing email → update auth_id) — works |
| User cancels Google consent | Returns to `/signup` — `onAuthStateChange` fires `SIGNED_OUT` → stays on Step 1, no data lost |
| OAuth provider returns no name | `exchangeTokenForUser` already falls back to email as username |

#### Summary

Social OAuth is **feasible** and the Supabase infrastructure already supports it. The main work is:
1. Creating the callback route (new file, ~30 lines)
2. Adding OAuth buttons + `signInWithOAuth` call in Step 1
3. Making the backend store OAuth-provided names
4. Updating the multi-step flow to skip email verification for OAuth users

The callback route **also** enables the email verification flow (Step 2 receives the verification redirect), so it's a necessary prerequisite regardless.

---

### Data Storage Gaps: What Gets Stored vs What the Profile Page Needs

Tracing the full data flow from signup to database reveals **4 gaps** that must be addressed before a profile page can display user data.

#### Gap 1: No Name Fields in Signup

The current form only captures email + password. `fullName` is hardcoded as `''`:

```ts
// signup-form.tsx:82
await signUpWithEmail(values.email, values.password, '');  // empty string!
```

The design doc's Step 1 adds `firstName` and `lastName` fields, but these are not yet passed to the backend or stored in the `users` table.

#### Gap 2: `users` Table Has No Name Column

The `users` table schema (inferred from all backend code):

| Column | Type | Currently Stores |
|--------|------|-----------------|
| `user_id` | integer (PK) | Auto-increment |
| `auth_id` | text | Supabase Auth UID |
| `email` | text | User's email |
| `username` | text | **Empty string** (never populated) |
| `last_signed_in` | timestamptz | ISO timestamp |
| `preferred_currency` | text | `'USD'` |

**No `first_name`, `last_name`, `display_name`, or `avatar_url` column exists.**

Additionally, the `display_name` passed via Supabase `options.data.display_name` is stored in Supabase Auth's internal `auth.users.raw_user_meta_data` — a completely separate system from the project's `users` table. The backend never reads from Supabase Auth metadata; it only uses the request body fields.

#### Gap 3: Frontend `User` Type Doesn't Match Backend Response

The frontend expects (from `web/src/features/auth/types/auth.types.ts`):

```ts
export interface User {
  id: string;
  email: string;
  displayName: string | null;
  photoURL: string | null;
}
```

But the backend returns DB columns:

```json
{ "user_id": 1, "email": "a@b.com", "username": "", "auth_id": "...", "last_signed_in": "...", "preferred_currency": "USD" }
```

There is no mapping layer — `displayName` and `photoURL` end up as `undefined` on the frontend.

#### Gap 4: No Read-Only Profile Endpoint

The only user endpoint is `POST /users/sync` (upsert). There is **no `GET /users/me`** to fetch the current user's profile. Every "read" is actually a write (updating `last_signed_in`). There is also no backend route to update individual profile fields (name, currency, etc.).

#### Profile Page

The profile page at `web/src/app/(authenticated)/profile/page.tsx` is a stub:

```tsx
export default function ProfilePage() {
  return (
    <div>
      <h1 className="text-2xl font-bold">Profile Page</h1>
      <p>This page is under construction.</p>
    </div>
  );
}
```

It displays nothing and makes no API calls.

#### What Must Change to Show User Data on Profile

| # | Change | Backend/Frontend |
|---|--------|------------------|
| 1 | Add `first_name TEXT` and `last_name TEXT` columns to `users` table | Supabase Dashboard (ALTER TABLE) |
| 2 | Update `POST /users/sync` to accept `first_name` and `last_name` in request body and write them | `backend/api/users.py` |
| 3 | Create `GET /users/me` endpoint that reads the profile without writing | `backend/api/users.py` — new route |
| 4 | (Optional) Create `PATCH /users/me` endpoint for profile editing | `backend/api/users.py` — new route |
| 5 | Update frontend `User` type and mapping to match backend response fields | `web/src/features/auth/types/auth.types.ts` + mapping in `auth.service.ts` |
| 6 | Build profile page UI to display and edit user data | `web/src/app/(authenticated)/profile/page.tsx` |

**All of these are prerequisites for Phase 1 Step 1** (adding name fields to the signup form) since captured data must be stored somewhere.

**All of these are prerequisites for Phase 1 Step 1** (adding name fields to the signup form) since captured data must be stored somewhere. See the [Migration Steps](#migration-steps-ordered) section above for the full ordered Phase 1 plan.