const get = (id) => document.getElementById(id);
let videos = [];
let selectedRunId = null;

function node(tag, className, value) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (value !== undefined) item.textContent = String(value);
  return item;
}
function time(ms) {
  const total = Math.max(0, Number(ms) || 0);
  const minutes = Math.floor(total / 60000);
  const seconds = ((total % 60000) / 1000).toFixed(1).padStart(4, '0');
  return String(minutes).padStart(2, '0') + ':' + seconds;
}
function date(value) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? '时间未知' : parsed.toLocaleString('zh-CN', {hour12: false});
}
function runUrl(runId, suffix) { return '/api/runs/' + encodeURIComponent(runId) + (suffix || ''); }
function setTab(name) {
  document.querySelectorAll('.tab').forEach((button) => {
    const active = button.dataset.tab === name;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  ['overview', 'files'].forEach((tab) => { get('tab-' + tab).hidden = tab !== name; });
}
function runKind(run) {
  return run.kind || (run.complete ? 'baseline' : 'test');
}
function runLabel(run) {
  const kind = runKind(run);
  return (kind === 'current' ? '推荐 · 完整规格运行' : kind === 'baseline' ? '旧版 · 仅视频描述' : '测试 · 部分片段') + ' · ' + run.event_count + ' 条';
}
function renderMarkdown(markdown) {
  const container = get('summary-content');
  container.replaceChildren();
  let list = null;
  for (const raw of markdown.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) { list = null; continue; }
    if (line.startsWith('# ')) {
      container.append(node('h1', '', line.slice(2))); list = null;
    } else if (line.startsWith('## ')) {
      container.append(node('h2', '', line.slice(3))); list = null;
    } else if (line.startsWith('- ')) {
      if (!list) { list = node('ul'); container.append(list); }
      list.append(node('li', '', line.slice(2)));
    } else {
      container.append(node('p', '', line)); list = null;
    }
  }
}
function renderVideos() {
  const container = get('video-list');
  container.replaceChildren();
  get('video-count').textContent = String(videos.length);
  for (const video of videos) {
    const group = node('div', 'video-group');
    const selected = video.runs.some((run) => run.id === selectedRunId);
    const button = node('button', 'video-item' + (selected ? ' active' : ''));
    button.type = 'button';
    button.append(node('span', 'video-name', video.name));
    button.append(node('span', 'video-meta', video.runs.length + ' 次分析运行'));
    button.addEventListener('click', () => loadRun(video.preferred_run_id));
    group.append(button);
    if (selected) {
      const options = node('div', 'run-options');
      const preferred = video.runs.find((run) => run.id === video.preferred_run_id);
      if (preferred) {
        const option = node('button', 'run-option primary' + (preferred.id === selectedRunId ? ' active' : ''));
        option.type = 'button';
        option.append(node('span', '', runLabel(preferred)), node('small', '', preferred.id));
        option.addEventListener('click', () => loadRun(preferred.id));
        options.append(option);
      }
      const others = video.runs.filter((run) => run.id !== video.preferred_run_id);
      if (others.length) {
        const archive = node('details', 'run-archive');
        archive.open = others.some((run) => run.id === selectedRunId);
        archive.append(node('summary', '', '旧版与测试记录（' + others.length + '）'));
        for (const run of others) {
          const option = node('button', 'run-option' + (run.id === selectedRunId ? ' active' : ''));
          option.type = 'button';
          option.append(node('span', '', runLabel(run)), node('small', '', run.id));
          option.addEventListener('click', () => loadRun(run.id));
          archive.append(option);
        }
        options.append(archive);
      }
      group.append(options);
    }
    container.append(group);
  }
}
function renderWarnings(warnings) {
  const container = get('warnings');
  container.replaceChildren();
  container.hidden = !Array.isArray(warnings) || warnings.length === 0;
  if (container.hidden) return;
  container.append(node('strong', '', '结果提示'));
  const list = node('ul');
  warnings.forEach((warning) => list.append(node('li', '', warning)));
  container.append(list);
}
function showImage(src, caption) {
  get('image-large').src = src;
  get('image-caption').textContent = caption;
  get('image-dialog').showModal();
}
function renderEvents(events, runId) {
  const container = get('event-list');
  container.replaceChildren();
  if (!events.length) { container.append(node('div', 'state-card', '本次运行没有识别到可展示的事件。')); return; }
  for (const event of events) {
    if (!event || typeof event !== 'object') continue;
    const card = node('article', 'event-card');
    const side = node('div', 'event-time');
    side.append(node('span', 'event-index', event.id || 'EVENT'));
    side.append(node('span', '', time(event.start_ms)));
    side.append(node('span', '', '— ' + time(event.end_ms)));
    card.append(side);
    const body = node('div', 'event-body');
    body.append(node('p', '', event.action || '未提供描述'));
    const tags = node('div', 'event-tags');
    tags.append(node('span', 'event-tag', event.person_id || '人物未关联'));
    tags.append(node('span', 'event-tag', event.status || '状态未知'));
    if (event.review_required) tags.append(node('span', 'event-tag', '待人工复核'));
    body.append(tags);
    const gallery = node('div', 'evidence-grid');
    for (const evidence of (Array.isArray(event.evidence) ? event.evidence : [])) {
      if (!evidence || typeof evidence.image !== 'string' || !/^evidence\/[A-Za-z0-9][A-Za-z0-9._-]*\.(jpg|jpeg|png|webp)$/i.test(evidence.image)) continue;
      const filename = evidence.image.slice('evidence/'.length);
      const src = runUrl(runId, '/evidence/' + encodeURIComponent(filename));
      const caption = (event.id || '事件') + ' · ' + time(evidence.timestamp_ms) + ' · ' + (evidence.frame_id || filename);
      const button = node('button', 'evidence-button');
      button.type = 'button';
      button.setAttribute('aria-label', '查看证据帧 ' + caption);
      const image = node('img');
      image.src = src;
      image.alt = caption;
      image.loading = 'lazy';
      button.append(image, node('span', '', time(evidence.timestamp_ms)));
      button.addEventListener('click', () => showImage(src, caption));
      gallery.append(button);
    }
    body.append(gallery);
    card.append(body);
    container.append(card);
  }
}
function renderDownloads(runId, downloads) {
  const container = get('download-list');
  container.replaceChildren();
  const descriptions = {
    'summary.md': ['中文摘要', '给人阅读，概括事件和限制'],
    'result.json': ['结构化结果', '事件、时间、人物标记及证据引用'],
    'tracks.json': ['人物轨迹', '局部轨迹和待复核相似候选，不代表真实人数'],
    'transcript.json': ['语音转写', '仅在识别出可信语音时生成'],
    'manifest.json': ['运行记录', '模型、参数、版本和运行时间'],
  };
  for (const filename of ['summary.md', 'result.json', 'tracks.json', 'transcript.json', 'manifest.json']) {
    if (!downloads.includes(filename)) continue;
    const link = node('a', 'download-link');
    link.append(node('strong', '', descriptions[filename][0] + ' ↗'), node('span', '', descriptions[filename][1]), node('code', '', filename));
    link.href = runUrl(runId, '/files/' + filename);
    container.append(link);
  }
  get('summary-download').href = runUrl(runId, '/files/summary.md');
}
function renderGuidance(match) {
  const container = get('run-guidance');
  container.replaceChildren();
  const kind = match ? runKind(match.run) : 'test';
  const title = kind === 'current' ? '当前应看的完整结果' : kind === 'baseline' ? '这是早期对照结果' : '这是短片测试记录';
  const description = kind === 'current'
    ? '按 MVP 规格运行了整条视频，包含检测、跟踪与事件证据。人物轨迹会碎片化，编号和动作仍需人工核对。'
    : kind === 'baseline'
      ? '只用视频大模型按固定片段描述画面；没有人物检测、跟踪和语音转写。请以完整规格运行为主。'
      : '只处理了部分视频，用来检查流水线能否工作；“部分分析”不表示整条视频已分析完。';
  container.append(node('strong', '', title), node('span', '', description));
  if (match && match.run.id !== match.video.preferred_run_id) {
    const link = node('button', 'guidance-link', '查看推荐的完整结果 →');
    link.type = 'button';
    link.addEventListener('click', () => loadRun(match.video.preferred_run_id));
    container.append(link);
  }
}
function renderRun(detail) {
  const match = videos.flatMap((video) => video.runs.map((run) => ({video, run}))).find((pair) => pair.run.id === detail.id);
  const result = detail.result;
  const events = Array.isArray(result.events) ? result.events : [];
  const people = Array.isArray(result.people) ? result.people : [];
  const frameCount = events.reduce((sum, event) => sum + (event && Array.isArray(event.evidence) ? event.evidence.length : 0), 0);
  get('video-title').textContent = match ? match.video.name : '视频结果';
  get('run-subtitle').textContent = detail.id + ' · ' + (detail.manifest.model || (detail.manifest.models && detail.manifest.models.vlm) || '模型未知') + ' · ' + date(detail.manifest.created_at);
  get('run-status').textContent = result.complete ? '完整分析' : '部分分析';
  get('run-status').classList.toggle('partial', !result.complete);
  renderGuidance(match);
  get('video-duration').textContent = time(result.video && result.video.duration_ms);
  get('event-count').textContent = String(events.length);
  get('evidence-count').textContent = String(frameCount);
  get('person-count').textContent = String(people.length);
  renderMarkdown(detail.summary);
  renderWarnings(result.warnings);
  renderEvents(events, detail.id);
  get('json-content').textContent = JSON.stringify(result, null, 2);
  get('manifest-content').textContent = JSON.stringify(detail.manifest, null, 2);
  renderDownloads(detail.id, detail.downloads || ['summary.md', 'result.json', 'manifest.json']);
  get('loading').hidden = true;
  get('error').hidden = true;
  get('empty').hidden = true;
  get('run-view').hidden = false;
}
async function loadRun(runId) {
  get('loading').hidden = false;
  get('run-view').hidden = true;
  try {
    const response = await fetch(runUrl(runId));
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const detail = await response.json();
    selectedRunId = runId;
    history.replaceState(null, '', '?run=' + encodeURIComponent(runId));
    renderVideos();
    renderRun(detail);
  } catch (error) {
    get('loading').hidden = true;
    get('error').hidden = false;
    get('error').textContent = '读取运行结果失败：' + error.message;
  }
}
async function boot() {
  document.querySelectorAll('.tab').forEach((button) => button.addEventListener('click', () => setTab(button.dataset.tab)));
  get('image-close').addEventListener('click', () => get('image-dialog').close());
  get('image-dialog').addEventListener('click', (event) => { if (event.target === get('image-dialog')) get('image-dialog').close(); });
  try {
    const response = await fetch('/api/videos');
    if (!response.ok) throw new Error('HTTP ' + response.status);
    videos = await response.json();
    get('loading').hidden = true;
    if (!videos.length) { get('empty').hidden = false; return; }
    const requested = new URLSearchParams(location.search).get('run');
    const available = videos.flatMap((video) => video.runs.map((run) => run.id));
    await loadRun(requested && available.includes(requested) ? requested : videos[0].preferred_run_id);
  } catch (error) {
    get('loading').hidden = true;
    get('error').hidden = false;
    get('error').textContent = '无法连接结果服务：' + error.message;
  }
}
boot();
