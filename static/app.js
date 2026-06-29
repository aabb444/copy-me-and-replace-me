/* ═══════════════════════════════════════════════════
   copy me and replace me — 前端交互
   功能: 日历点击 / 笔记卡片 / 标签过滤
   ═══════════════════════════════════════════════════ */

(function () {
  'use strict';

  let calendarYear = typeof INITIAL_YEAR !== 'undefined' ? INITIAL_YEAR : new Date().getFullYear();
  let calendarMonth = typeof INITIAL_MONTH !== 'undefined' ? INITIAL_MONTH : new Date().getMonth() + 1;
  let activeTag = null;
  let allNotesCache = [];

  // ═══════════════════════════════
  // Toast
  // ═══════════════════════════════

  function showToast(msg, type) {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = 'toast ' + type;
    clearTimeout(el._timer);
    el._timer = setTimeout(() => el.classList.add('hidden'), 3500);
  }

  function setLoading(btnId, loading) {
    const btn = document.getElementById(btnId);
    if (loading) btn.classList.add('loading');
    else btn.classList.remove('loading');
  }

  // ═══════════════════════════════
  // TASK
  // ═══════════════════════════════

  document.getElementById('taskForm').addEventListener('submit', async function (e) {
    e.preventDefault();
    const input = document.getElementById('taskInput');
    const text = input.value.trim();
    if (!text) return;

    setLoading('taskBtn', true);
    try {
      const resp = await fetch('/api/task', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      const data = await resp.json();
      if (data.success) {
        showToast('任务已添加', 'success');
        input.value = '';
        refreshTaskList();
        refreshCalendar();
      } else {
        showToast(data.error || '创建失败', 'error');
      }
    } catch (err) {
      showToast('网络错误', 'error');
    } finally {
      setLoading('taskBtn', false);
    }
  });

  async function completeTask(taskId) {
    const item = document.querySelector(`.task-item[data-id="${taskId}"]`);
    if (item) item.classList.add('completing');
    try {
      const resp = await fetch(`/api/task/${taskId}/complete`, { method: 'PATCH' });
      const data = await resp.json();
      if (data.success) {
        showToast('任务完成', 'success');
        setTimeout(() => { if (item) item.remove(); updateTaskCount(); refreshCalendar(); }, 300);
      }
    } catch (err) {
      showToast('操作失败', 'error');
      if (item) item.classList.remove('completing');
    }
  }
  window.completeTask = completeTask;

  async function refreshTaskList() {
    try {
      const resp = await fetch('/api/tasks/active');
      const tasks = await resp.json();
      const list = document.getElementById('taskList');
      const count = document.getElementById('taskCount');

      if (!tasks.length) {
        list.innerHTML = '<div class="empty-state">暂无未完成任务</div>';
        count.textContent = '0';
        return;
      }

      count.textContent = tasks.length;
      list.innerHTML = tasks.map(t => `
        <div class="task-item" data-id="${t.id}">
          <button class="task-check" onclick="completeTask('${t.id}')">✓</button>
          <div class="task-body">
            <span class="task-title">${esc(t.title)}</span>
            <span class="task-meta">
              <span class="task-date">${t.date}</span>
              ${t.time ? `<span class="task-time">${t.time}</span>` : ''}
              <span class="task-priority priority-${t.priority}">${t.priority}</span>
            </span>
          </div>
        </div>
      `).join('');
    } catch (err) { console.error(err); }
  }

  function updateTaskCount() {
    const n = document.querySelectorAll('.task-item:not(.completing)').length;
    document.getElementById('taskCount').textContent = n;
  }
  window.updateTaskCount = updateTaskCount;

  // ═══════════════════════════════
  // NOTE
  // ═══════════════════════════════

  document.getElementById('noteForm').addEventListener('submit', async function (e) {
    e.preventDefault();
    const input = document.getElementById('noteInput');
    const text = input.value.trim();
    if (!text) return;

    setLoading('noteBtn', true);
    try {
      const resp = await fetch('/api/note', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      const data = await resp.json();
      if (data.success) {
        const note = data.note;
        showToast(`笔记已保存 - ${(note.tags||[]).slice(0,3).join(', ')}`, 'success');
        input.value = '';
        await Promise.all([refreshTags(), loadAllNotes()]);
      } else {
        showToast(data.error || '保存失败', 'error');
      }
    } catch (err) {
      showToast('网络错误', 'error');
    } finally {
      setLoading('noteBtn', false);
    }
  });

  // ═══════════════════════════════
  // NOTES DISPLAY
  // ═══════════════════════════════

  async function loadAllNotes() {
    activeTag = null;
    document.querySelectorAll('.tag-item').forEach(el => el.classList.remove('active'));
    document.getElementById('notesTitle').textContent = '全部笔记';

    try {
      const resp = await fetch('/api/notes/all');
      const notes = await resp.json();
      allNotesCache = notes;
      renderNotes(notes);
    } catch (err) {
      document.getElementById('notesGrid').innerHTML = '<div class="empty-state">加载失败</div>';
    }
  }
  window.loadAllNotes = loadAllNotes;

  function renderNotes(notes) {
    const grid = document.getElementById('notesGrid');
    const count = document.getElementById('notesCount');
    count.textContent = notes.length;

    if (!notes.length) {
      grid.innerHTML = '<div class="empty-state">暂无笔记</div>';
      return;
    }

    grid.innerHTML = notes.map(n => {
      const tags = n.tags || [];
      const preview = n.preview || '';
      return `
        <div class="note-card" onclick="showNote('${esc(n.filename)}')">
          <div class="note-card-tags">
            ${tags.slice(0, 4).map(t => `<span class="note-card-tag">#${esc(t)}</span>`).join('')}
            ${tags.length > 4 ? `<span class="note-card-tag">+${tags.length - 4}</span>` : ''}
          </div>
          <div class="note-card-title">${esc(n.title || n.filename)}</div>
          <div class="note-card-preview">${esc(preview)}</div>
          <div class="note-card-footer">
            <span>${n.date || ''}</span>
            <span class="note-card-type">${n.type || 'note'}</span>
          </div>
        </div>`;
    }).join('');
  }

  // ═══════════════════════════════
  // TAG FILTER
  // ═══════════════════════════════

  async function refreshTags() {
    try {
      const resp = await fetch('/api/tags');
      const tags = await resp.json();
      const cloud = document.getElementById('tagCloud');
      document.getElementById('tagTotal').textContent = Object.keys(tags).length;

      if (!Object.keys(tags).length) {
        cloud.innerHTML = '<div class="empty-state" style="padding:8px">暂无标签</div>';
        return;
      }

      cloud.innerHTML = Object.entries(tags).map(([tag, info]) =>
        `<div class="tag-item${activeTag === tag ? ' active' : ''}" data-tag="${esc(tag)}"
            onclick="filterByTag('${esc(tag)}')">
          <span>#${esc(tag)}</span>
          <span class="tag-count">${info.count}</span>
        </div>`
      ).join('');
    } catch (err) { console.error(err); }
  }
  window.refreshTags = refreshTags;

  async function filterByTag(tag) {
    if (activeTag === tag) {
      // deselect
      activeTag = null;
      document.querySelectorAll('.tag-item').forEach(el => el.classList.remove('active'));
      document.getElementById('notesTitle').textContent = '全部笔记';
      renderNotes(allNotesCache);
      return;
    }

    activeTag = tag;
    document.querySelectorAll('.tag-item').forEach(el => {
      el.classList.toggle('active', el.dataset.tag === tag);
    });
    document.getElementById('notesTitle').textContent = '# ' + tag;

    try {
      const resp = await fetch(`/api/notes?tag=${encodeURIComponent(tag)}`);
      const notes = await resp.json();
      renderNotes(notes);
    } catch (err) {
      showToast('加载失败', 'error');
    }
  }
  window.filterByTag = filterByTag;

  // ═══════════════════════════════
  // CALENDAR — SELECT DATE
  // ═══════════════════════════════

  async function selectDate(dateStr) {
    // remove previous selection
    document.querySelectorAll('.calendar-table td').forEach(td => td.classList.remove('selected'));

    // highlight selected
    const cells = document.querySelectorAll(`.calendar-table td[data-date="${dateStr}"]`);
    cells.forEach(td => td.classList.add('selected'));

    // fetch tasks for this date
    try {
      const resp = await fetch(`/api/tasks/date?date=${dateStr}`);
      const data = await resp.json();
      const allTasks = [...(data.active || []), ...(data.archived || [])];

      const panel = document.getElementById('dayDetail');
      if (!allTasks.length) {
        panel.innerHTML = `<div class="day-detail"><div class="day-detail-title">${dateStr}</div>当天无任务</div>`;
        return;
      }

      const completed = data.archived || [];
      const active = data.active || [];

      panel.innerHTML = `<div class="day-detail">
        <div class="day-detail-title">${dateStr} — ${allTasks.length} 项</div>
        ${[...active, ...completed].map(t => `
          <div class="day-detail-item">
            ${t.status === 'completed' ? '✅' : '⬜'}
            ${t.time ? `<span class="time-tag">${t.time}</span>` : ''}
            ${esc(t.title)}
          </div>
        `).join('')}
      </div>`;
    } catch (err) {
      console.error(err);
    }
  }
  window.selectDate = selectDate;

  // ═══════════════════════════════
  // CALENDAR — NAV
  // ═══════════════════════════════

  async function changeMonth(delta) {
    calendarMonth += delta;
    if (calendarMonth > 12) { calendarMonth = 1; calendarYear++; }
    if (calendarMonth < 1) { calendarMonth = 12; calendarYear--; }
    await loadCalendar();
  }
  window.changeMonth = changeMonth;

  async function goToday() {
    const now = new Date();
    calendarYear = now.getFullYear();
    calendarMonth = now.getMonth() + 1;
    await loadCalendar();
  }
  window.goToday = goToday;

  async function loadCalendar() {
    try {
      const resp = await fetch(`/api/calendar?year=${calendarYear}&month=${calendarMonth}`);
      const cal = await resp.json();
      renderCalendar(cal);
    } catch (err) { console.error(err); }
  }
  window.loadCalendar = loadCalendar;

  function renderCalendar(cal) {
    document.getElementById('calendarTitle').textContent = `${cal.month_name} ${cal.year}`;
    const tbody = document.getElementById('calendarBody');
    tbody.innerHTML = cal.weeks.map(week =>
      '<tr>' + week.map(day => {
        if (!day) return '<td></td>';
        const cls = [];
        if (day.is_today) cls.push('today');
        if (day.count > 0) cls.push('has-tasks');
        return `<td class="${cls.join(' ')}" data-date="${day.date}" onclick="selectDate('${day.date}')">
          <span class="day-num">${day.day}</span>
          ${day.count > 0 ? `<span class="day-dot">${day.count}</span>` : ''}
        </td>`;
      }).join('') + '</tr>'
    ).join('');
  }

  async function refreshCalendar() { await loadCalendar(); }
  window.refreshCalendar = refreshCalendar;

  // ═══════════════════════════════
  // NOTE MODAL
  // ═══════════════════════════════

  async function showNote(filename) {
    try {
      const resp = await fetch(`/api/note/${encodeURIComponent(filename)}`);
      const note = await resp.json();
      if (!note || note.error) { showToast('笔记不存在', 'error'); return; }

      const content = note.content || '';
      const parts = content.split('---');
      let body = content;
      let meta = {};
      if (parts.length >= 3) {
        meta = parseFrontmatter(parts[1]);
        body = parts.slice(2).join('---').trim();
      }

      const tags = meta.tags || [];
      const overlay = document.createElement('div');
      overlay.className = 'modal-overlay';
      overlay.innerHTML = `
        <div class="modal-content">
          <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">关闭</button>
          <h2>${esc(meta.title || filename)}</h2>
          <div class="modal-tags">
            ${tags.map(t => `<span class="modal-tag">#${esc(t)}</span>`).join('')}
          </div>
          <div style="font-size:12px;color:var(--text-muted);margin-bottom:12px">${meta.date || ''} · ${meta.type || 'note'}</div>
          <div class="modal-body">${esc(body)}</div>
        </div>`;
      overlay.addEventListener('click', function(e) { if (e.target === this) this.remove(); });
      document.body.appendChild(overlay);
    } catch (err) { showToast('加载失败', 'error'); }
  }
  window.showNote = showNote;

  function parseFrontmatter(fm) {
    const meta = {};
    let currentKey = null;
    fm.split('\n').forEach(line => {
      const listMatch = line.match(/^\s{2}-\s(.+)/);
      if (listMatch && currentKey) {
        if (!meta[currentKey]) meta[currentKey] = [];
        meta[currentKey].push(listMatch[1].trim());
        return;
      }
      const kvMatch = line.match(/^(\w+):\s?(.+)?$/);
      if (kvMatch) {
        currentKey = kvMatch[1];
        const val = kvMatch[2] ? kvMatch[2].trim() : null;
        if (val) {
          if (val.startsWith('[')) {
            try { meta[currentKey] = JSON.parse(val.replace(/'/g, '"')); }
            catch(e) { meta[currentKey] = val; }
          } else {
            meta[currentKey] = val;
          }
        }
      }
    });
    return meta;
  }

  // ═══════════════════════════════
  // ESCAPE
  // ═══════════════════════════════

  function esc(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  // ═══════════════════════════════
  // INIT
  // ═══════════════════════════════

  document.addEventListener('DOMContentLoaded', () => {
    loadAllNotes();
  });

})();
