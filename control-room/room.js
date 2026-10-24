document.documentElement.classList.add('js');

function openLinkedReview() {
  const linked = document.getElementById(location.hash.slice(1));
  if (linked?.matches('details')) linked.open = true;
}
openLinkedReview();
window.addEventListener('hashchange', openLinkedReview);

let drag = null;
let refreshing = false;

function selectFlow() {
  let id = location.hash.startsWith('#flow-') ? location.hash.slice(6) : '';
  if (id && !document.getElementById(`flow-${id}`)) {
    const matches = [...document.querySelectorAll('.flow-detail')].filter(detail => detail.dataset.bindings?.split(' ').includes(id));
    if (matches.length === 1) {
      id = matches[0].id.slice(5);
      history.replaceState(null, '', `#flow-${id}`);
    }
  }
  const related = new Set(id ? [id] : []);
  const edges = [...document.querySelectorAll('.flow-edge')];
  // Trace upstream and downstream separately; a shared reviewer does not imply sibling ownership.
  for (const direction of ['from', 'to']) {
    const seen = new Set(related.size ? [id] : []);
    let changed = true;
    while (changed) {
      changed = false;
      for (const edge of edges) {
        const other = direction === 'from' ? 'to' : 'from';
        if (seen.has(edge.dataset[direction]) && !seen.has(edge.dataset[other])) {
          seen.add(edge.dataset[other]);
          changed = true;
        }
      }
    }
    seen.forEach(value => related.add(value));
  }
  document.querySelectorAll('.flow-node').forEach(node => {
    node.classList.toggle('selected', node.dataset.node === id);
    node.classList.toggle('related', related.has(node.dataset.node));
  });
  edges.forEach(edge => edge.classList.toggle('related', related.has(edge.dataset.from) && related.has(edge.dataset.to)));
  document.querySelectorAll('.flow-detail').forEach(detail => detail.classList.toggle('selected', detail.id === `flow-${id}`));
}
selectFlow();
window.addEventListener('hashchange', selectFlow);

function zoomFlow(action) {
  const graph = document.querySelector('.flow-graph');
  if (!graph) return;
  if (action === 'fit') {
    graph.setAttribute('viewBox', graph.dataset.fit);
    return;
  }
  const box = graph.viewBox.baseVal;
  const scale = action === 'in' ? 0.8 : 1.25;
  const width = box.width * scale;
  if (width < 200 || width > 6000) return;
  const height = box.height * scale;
  graph.setAttribute('viewBox', `${box.x + (box.width - width) / 2} ${box.y + (box.height - height) / 2} ${width} ${height}`);
}

document.addEventListener('click', event => {
  const node = event.target.closest('.flow-node');
  if (node) {
    event.preventDefault();
    history.replaceState(null, '', node.getAttribute('href'));
    selectFlow();
  }
  const zoom = event.target.closest('[data-zoom]');
  if (zoom) zoomFlow(zoom.dataset.zoom);
});
document.addEventListener('pointerdown', event => {
  const graph = event.target.closest('.flow-graph');
  if (!graph || event.target.closest('a') || event.button !== 0) return;
  const box = graph.viewBox.baseVal;
  drag = {graph, x: event.clientX, y: event.clientY, box: [box.x, box.y, box.width, box.height]};
  graph.setPointerCapture(event.pointerId);
  graph.classList.add('dragging');
});
document.addEventListener('pointermove', event => {
  if (!drag) return;
  const [x, y, width, height] = drag.box;
  const scale = Math.max(width / drag.graph.clientWidth, height / drag.graph.clientHeight);
  drag.graph.setAttribute('viewBox', `${x - (event.clientX - drag.x) * scale} ${y - (event.clientY - drag.y) * scale} ${width} ${height}`);
});
function endDrag() {
  drag?.graph.classList.remove('dragging');
  drag = null;
}
document.addEventListener('pointerup', endDrag);
document.addEventListener('pointercancel', endDrag);
document.addEventListener('wheel', event => {
  if (event.target.closest('.flow-graph') && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    zoomFlow(event.deltaY < 0 ? 'in' : 'out');
  }
}, {passive: false});
document.addEventListener('keydown', event => {
  if (!event.target.matches('.flow-graph')) return;
  if (['+', '=', '-', '0'].includes(event.key)) {
    event.preventDefault();
    zoomFlow(event.key === '0' ? 'fit' : event.key === '-' ? 'out' : 'in');
  }
  const directions = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]};
  if (directions[event.key]) {
    event.preventDefault();
    const [dx, dy] = directions[event.key];
    const box = event.target.viewBox.baseVal;
    event.target.setAttribute('viewBox', `${box.x + dx * box.width / 10} ${box.y + dy * box.height / 10} ${box.width} ${box.height}`);
  }
});

document.addEventListener('change', event => {
  if (event.target.id === 'project') event.target.form.requestSubmit();
});
document.addEventListener('submit', async event => {
  const form = event.target;
  if (!form.matches('form.navigate')) return;
  event.preventDefault();
  const button = form.querySelector('button');
  const notice = document.querySelector('#notice');
  button.disabled = true;
  try {
    const response = await fetch(form.action, {
      method: 'POST',
      headers: {Accept: 'application/json'},
      body: new URLSearchParams(new FormData(form)),
      signal: AbortSignal.timeout(30000),
    });
    if (!response.ok) throw new Error(await response.text());
    notice.textContent = 'Pane opened.';
  } catch (error) {
    notice.textContent = `Could not open pane: ${error.message}`;
  } finally {
    button.disabled = false;
  }
});

// Keep expanded evidence and keyboard focus intact while fresh snapshots arrive.
async function refresh() {
  if (location.pathname !== '/' || document.hidden || refreshing || drag) return;
  const graph = document.querySelector('.flow-graph');
  const active = document.activeElement;
  if (document.querySelector('details[open]') || active?.matches('select,input,summary')) return;
  if (active?.matches('button') && !active.hasAttribute('data-zoom')) return;
  if (!graph && active?.matches('a')) return;
  refreshing = true;
  try {
    const response = await fetch(location.href, {signal: AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const next = new DOMParser().parseFromString(await response.text(), 'text/html').querySelector('main');
    if (!next) throw new Error('Invalid page');
    const nextGraph = next.querySelector('.flow-graph');
    if (graph && nextGraph) {
      if (graph.dataset.fit === nextGraph.dataset.fit) nextGraph.setAttribute('viewBox', graph.getAttribute('viewBox'));
      const previous = new Map([...graph.querySelectorAll('.flow-node')].map(node => [node.dataset.node, node.dataset.state]));
      nextGraph.querySelectorAll('.flow-node').forEach(node => {
        if (previous.has(node.dataset.node) && previous.get(node.dataset.node) !== node.dataset.state) node.classList.add('just-changed');
      });
    }
    const selected = active?.getAttribute('data-node');
    const zoom = active?.getAttribute('data-zoom');
    const scroll = document.querySelector('.flow-inspector')?.scrollTop;
    const bindings = document.querySelector('.flow-detail.selected')?.dataset.bindings?.split(' ').filter(Boolean) || [];
    const successors = [...next.querySelectorAll('.flow-detail')].filter(detail =>
      detail.dataset.bindings?.split(' ').some(binding => bindings.includes(binding)));
    if (successors.length === 1) history.replaceState(null, '', `#${successors[0].id}`);
    document.querySelector('main').replaceWith(next);
    selectFlow();
    if (active === graph) nextGraph?.focus({preventScroll: true});
    if (selected) [...next.querySelectorAll('.flow-node')].find(node => node.dataset.node === selected)?.focus({preventScroll: true});
    if (zoom) [...next.querySelectorAll('[data-zoom]')].find(button => button.dataset.zoom === zoom)?.focus({preventScroll: true});
    if (scroll !== undefined) next.querySelector('.flow-inspector').scrollTop = scroll;
    document.documentElement.classList.remove('disconnected');
    document.querySelector('#notice').textContent = '';
  } catch (error) {
    document.documentElement.classList.add('disconnected');
    document.querySelector('#notice').textContent = 'Disconnected. Status may be out of date.';
    document.querySelectorAll('form.navigate button').forEach(button => { button.disabled = true; });
  } finally {
    refreshing = false;
  }
}
if (location.pathname === '/') {
  setInterval(refresh, document.querySelector('.flow-graph') ? 2000 : 15000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
}
