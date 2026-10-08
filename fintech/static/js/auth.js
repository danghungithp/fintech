/* FinViet Pro — login & registration-request pages */
(function () {
  'use strict';
  const { fetchJSON, postJSON, toast } = App;

  const el = (id) => document.getElementById(id);

  // FormSubmit blocks server-side calls from Vercel, so the visitor's browser
  // relays the notification itself and reports the outcome back to our API.
  const FORMSUBMIT_URL = 'https://formsubmit.co/ajax/mcpsoftware@gmail.com';

  async function relayRegistrationNotice(email, note) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    try {
      const resp = await fetch(FORMSUBMIT_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          _subject: `[FinViet Pro] Yêu cầu đăng ký tài khoản: ${email}`,
          email,
          ghi_chu: note || '(không có)',
          _template: 'table',
        }),
        signal: controller.signal,
      });
      const data = await resp.json().catch(() => ({}));
      return String(data.success).toLowerCase() === 'true';
    } catch (e) {
      return false;
    } finally {
      clearTimeout(timer);
    }
  }

  function initLogin() {
    const form = el('login-form');
    if (!form) return;
    // Already logged in? Jump straight to the journal.
    fetchJSON('/api/auth/me').then((data) => {
      if (data && data.user) window.location.href = '/so-giao-dich';
    }).catch(() => { /* not logged in */ });

    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const btn = el('login-btn');
      btn.disabled = true;
      btn.textContent = 'Đang đăng nhập...';
      try {
        await postJSON('/api/auth/login', {
          email: el('login-email').value.trim(),
          password: el('login-password').value,
        });
        toast('Đăng nhập thành công!', 'success', 'Chào mừng trở lại');
        const params = new URLSearchParams(window.location.search);
        const next = params.get('next');
        window.location.href = next && next.startsWith('/') ? next : '/phan-tich';
      } catch (err) {
        toast(err.message, 'error', 'Đăng nhập thất bại');
        btn.disabled = false;
        btn.textContent = 'Đăng nhập';
      }
    });
  }

  function initRegister() {
    const form = el('register-form');
    if (!form) return;
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const btn = el('register-btn');
      btn.disabled = true;
      btn.textContent = 'Đang gửi...';
      try {
        const email = el('register-email').value.trim();
        const note = el('register-note').value.trim();
        const relayed = await relayRegistrationNotice(email, note);
        const res = await postJSON('/api/register-request', { email, note, formsubmit_ok: relayed });
        el('register-form-wrap').classList.add('hidden');
        el('register-done').classList.remove('hidden');
        const extra = res.notified ? '' : ' (Yêu cầu đã được lưu, quản trị viên sẽ xem xét trong bảng quản trị.)';
        toast(`Đã gửi yêu cầu đăng ký tới quản trị viên.${extra}`, 'success', 'Đăng ký');
      } catch (err) {
        toast(err.message, 'error', 'Gửi yêu cầu thất bại');
        btn.disabled = false;
        btn.textContent = 'Gửi yêu cầu đăng ký';
      }
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    initLogin();
    initRegister();
  });
})();
