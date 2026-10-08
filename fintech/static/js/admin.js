/* FinViet Pro — admin panel (duyệt đăng ký, tạo user) */
(function () {
  'use strict';
  const { fmt, fetchJSON, postJSON, toast } = App;

  const el = (id) => document.getElementById(id);

  const STATUS_LABEL = { NEW: 'Chờ duyệt', APPROVED: 'Đã duyệt', REJECTED: 'Từ chối' };

  function statusBadge(status) {
    const tone = status === 'APPROVED' ? 'tone-up' : status === 'REJECTED' ? 'tone-down' : 'tone-neutral';
    return `<span class="badge ${tone}">${STATUS_LABEL[status] || fmt.escape(status)}</span>`;
  }

  function renderRequests(requests) {
    const pending = requests.filter((r) => (r.status || 'NEW') === 'NEW');
    el('admin-req-count').textContent = `${pending.length} chờ duyệt`;
    const rows = ['<tr><th>Thời gian</th><th>Email</th><th>Ghi chú</th><th>Thông báo</th><th>Trạng thái</th><th></th></tr>'];
    requests.forEach((r) => {
      const isNew = (r.status || 'NEW') === 'NEW';
      rows.push(`<tr>
        <td class="tnum small">${fmt.escape(r.created_at || '')}</td>
        <td><b>${fmt.escape(r.email)}</b></td>
        <td class="small muted" style="max-width:260px;white-space:normal;">${fmt.escape(r.note || '')}</td>
        <td class="small">${r.notified ? `✅ ${fmt.escape(r.notify_method || '')}` : '⏳ chưa gửi'}</td>
        <td>${statusBadge(r.status)}</td>
        <td>${isNew ? `
          <div class="flex" style="gap:4px;">
            <button class="btn btn-xs btn-primary req-approve" data-id="${r.id}" data-email="${fmt.escape(r.email)}" title="Duyệt: mở form tạo tài khoản">Duyệt</button>
            <button class="btn btn-xs btn-ghost req-reject" data-id="${r.id}" title="Từ chối yêu cầu">Từ chối</button>
          </div>` : ''}
        </td>
      </tr>`);
    });
    el('requests-table').innerHTML = rows.join('') +
      (requests.length ? '' : '<tr><td colspan="6" class="small muted" style="text-align:center;padding:16px;">Chưa có yêu cầu đăng ký nào</td></tr>');

    el('requests-table').querySelectorAll('.req-approve').forEach((btn) => {
      btn.addEventListener('click', () => {
        el('u-email').value = btn.dataset.email;
        el('u-name').focus();
        el('u-email').scrollIntoView({ behavior: 'smooth', block: 'center' });
        el('u-email').style.outline = '2px solid var(--accent)';
        setTimeout(() => { el('u-email').style.outline = ''; }, 1600);
        toast('Email đã điền sẵn — nhập mật khẩu cấp sẵn rồi bấm "Tạo tài khoản".', 'info', 'Duyệt yêu cầu');
      });
    });
    el('requests-table').querySelectorAll('.req-reject').forEach((btn) => {
      btn.addEventListener('click', async () => {
        if (!window.confirm('Từ chối yêu cầu đăng ký này?')) return;
        try {
          await postJSON(`/api/admin/requests/${btn.dataset.id}/status`, { status: 'REJECTED' });
          toast('Đã từ chối yêu cầu.', 'success', 'Quản trị');
          loadOverview();
        } catch (err) {
          toast(err.message, 'error', 'Quản trị');
        }
      });
    });
  }

  function renderUsers(users) {
    el('admin-user-count').textContent = `${users.length} tài khoản`;
    const rows = ['<tr><th>Thời gian tạo</th><th>Email</th><th>Tên</th><th>Vai trò</th><th>Trạng thái</th><th></th></tr>'];
    users.forEach((u) => {
      const active = !!u.active;
      rows.push(`<tr>
        <td class="tnum small">${fmt.escape(u.created_at || '')}</td>
        <td><b>${fmt.escape(u.email)}</b></td>
        <td>${fmt.escape(u.name || '')}</td>
        <td class="small">${fmt.escape(u.role || 'user')}</td>
        <td><span class="badge ${active ? 'tone-up' : 'tone-down'}">${active ? 'Hoạt động' : 'Bị khóa'}</span></td>
        <td><button class="btn btn-xs btn-ghost user-toggle" data-id="${u.id}" data-active="${active ? 1 : 0}">
          ${active ? 'Khóa' : 'Mở khóa'}</button></td>
      </tr>`);
    });
    el('users-table').innerHTML = rows.join('') +
      (users.length ? '' : '<tr><td colspan="6" class="small muted" style="text-align:center;padding:16px;">Chưa có tài khoản nào</td></tr>');

    el('users-table').querySelectorAll('.user-toggle').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const makeActive = btn.dataset.active !== '1';
        try {
          await postJSON(`/api/admin/users/${btn.dataset.id}/active`, { active: makeActive });
          toast(makeActive ? 'Đã mở khóa tài khoản.' : 'Đã khóa tài khoản.', 'success', 'Quản trị');
          loadOverview();
        } catch (err) {
          toast(err.message, 'error', 'Quản trị');
        }
      });
    });
  }

  async function loadOverview() {
    const overview = await fetchJSON('/api/admin/overview');
    renderRequests(overview.requests || []);
    renderUsers(overview.users || []);
  }

  function initGate() {
    const gateForm = el('admin-gate-form');
    if (!gateForm) return;
    gateForm.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      try {
        await postJSON('/api/admin/login', { password: el('admin-password').value });
        el('admin-gate').classList.add('hidden');
        el('admin-app').classList.remove('hidden');
        await loadOverview();
      } catch (err) {
        toast(err.message, 'error', 'Đăng nhập quản trị');
      }
    });
    el('admin-refresh').addEventListener('click', () => loadOverview().catch((e) => toast(e.message, 'error', 'Quản trị')));
    el('admin-logout').addEventListener('click', async () => {
      await postJSON('/api/admin/logout', {});
      window.location.reload();
    });
    el('user-form').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      try {
        await postJSON('/api/admin/users', {
          email: el('u-email').value.trim(),
          name: el('u-name').value.trim(),
          password: el('u-pass').value,
        });
        toast(`Đã tạo tài khoản cho ${el('u-email').value.trim()}.`, 'success', 'Quản trị');
        el('u-email').value = '';
        el('u-name').value = '';
        el('u-pass').value = '';
        loadOverview();
      } catch (err) {
        toast(err.message, 'error', 'Tạo tài khoản thất bại');
      }
    });
  }

  document.addEventListener('DOMContentLoaded', async () => {
    initGate();
    // Already unlocked this session? Skip the gate.
    try {
      const me = await fetchJSON('/api/auth/me');
      if (me && me.admin) {
        el('admin-gate').classList.add('hidden');
        el('admin-app').classList.remove('hidden');
        await loadOverview();
      }
    } catch (e) { /* gate stays */ }
  });
})();
