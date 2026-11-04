/**
 * KOS-Mappings Explorer - Frontend Application Logic
 * Implements Breadth-First-Search (BFS) shortest path finding across KOS mappings,
 * live multi-hop crosswalk routing, concept querying, and endpoint discovery.
 */

let GRAPH_DATA = null;
let ENDPOINTS = [];
let ENDPOINT_MAP = new Map();
let ADJACENCY = {};

// Initialize application on DOM content loaded
document.addEventListener("DOMContentLoaded", async () => {
  setupTabs();
  await loadApplicationData();
  setupPathfinder();
  setupQueryEngine();
  setupEndpointsView();
  setupTopologyView();
});

// --------------------------------------------------------------------------
// 1. Data Loading
// --------------------------------------------------------------------------
async function loadApplicationData() {
  try {
    const [graphResp, epResp] = await Promise.all([
      fetch("data/mappings_graph.json"),
      fetch("data/endpoints.json")
    ]);

    if (!graphResp.ok || !epResp.ok) {
      throw new Error(`Failed to load data files (HTTP ${graphResp.status} / ${epResp.status})`);
    }

    GRAPH_DATA = await graphResp.json();
    ENDPOINTS = await epResp.json();

    ENDPOINTS.forEach(ep => {
      ENDPOINT_MAP.set(ep.prefix.toLowerCase(), ep);
    });

    ADJACENCY = GRAPH_DATA.adjacency || {};
    console.log("KOS-Mappings loaded successfully:", GRAPH_DATA.stats);
  } catch (err) {
    console.error("Initialization error:", err);
    alert("Could not load mappings data. If testing locally, ensure you are using a local web server (e.g. python -m http.server).");
  }
}

// --------------------------------------------------------------------------
// 2. Navigation Tabs
// --------------------------------------------------------------------------
function setupTabs() {
  const tabs = document.querySelectorAll(".nav-tab");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      const targetId = tab.getAttribute("data-target");
      tabs.forEach(t => {
        t.classList.remove("active");
        t.setAttribute("aria-selected", "false");
      });
      tab.classList.add("active");
      tab.setAttribute("aria-selected", "true");

      document.querySelectorAll(".tab-section").forEach(sec => {
        sec.classList.remove("active");
      });
      const targetSection = document.getElementById(targetId);
      if (targetSection) targetSection.classList.add("active");
    });
  });
}

// --------------------------------------------------------------------------
// 3. Semantic Crosswalk Pathfinder (BFS Shortest Path)
// --------------------------------------------------------------------------
function setupPathfinder() {
  const selectSrc = document.getElementById("select-source-vocab");
  const selectTgt = document.getElementById("select-target-vocab");
  const filterSrc = document.getElementById("input-source-filter");
  const filterTgt = document.getElementById("input-target-filter");
  const btnFind = document.getElementById("btn-find-path");
  const btnSwap = document.getElementById("btn-swap-vocabs");

  if (!GRAPH_DATA || !GRAPH_DATA.nodes) return;

  // Populate vocabulary dropdowns
  const nodes = [...GRAPH_DATA.nodes].sort((a, b) => b.mapping_count - a.mapping_count);

  function renderSelectOptions(selectEl, filterText = "") {
    const q = filterText.toLowerCase().trim();
    const currentVal = selectEl.value;
    selectEl.innerHTML = "";

    nodes.forEach(node => {
      const match = !q || node.id.includes(q) || node.name.toLowerCase().includes(q) || node.category.toLowerCase().includes(q);
      if (match) {
        const opt = document.createElement("option");
        opt.value = node.id;
        opt.textContent = `${node.id.toUpperCase()} - ${node.name} (${node.mapping_count.toLocaleString()} rows)`;
        selectEl.appendChild(opt);
      }
    });

    if (currentVal && Array.from(selectEl.options).some(o => o.value === currentVal)) {
      selectEl.value = currentVal;
    } else if (selectEl.options.length > 0) {
      selectEl.selectedIndex = 0;
    }
  }

  renderSelectOptions(selectSrc);
  renderSelectOptions(selectTgt);

  // Set initial default selections
  if (selectSrc.querySelector("option[value='loinc']")) selectSrc.value = "loinc";
  if (selectTgt.querySelector("option[value='snomedct']")) selectTgt.value = "snomedct";

  updateVocabDetails("source-details", selectSrc.value);
  updateVocabDetails("target-details", selectTgt.value);

  // Filter events
  filterSrc.addEventListener("input", (e) => renderSelectOptions(selectSrc, e.target.value));
  filterTgt.addEventListener("input", (e) => renderSelectOptions(selectTgt, e.target.value));

  selectSrc.addEventListener("change", () => updateVocabDetails("source-details", selectSrc.value));
  selectTgt.addEventListener("change", () => updateVocabDetails("target-details", selectTgt.value));

  // Swap button
  btnSwap.addEventListener("click", () => {
    const tmp = selectSrc.value;
    selectSrc.value = selectTgt.value;
    selectTgt.value = tmp;
    updateVocabDetails("source-details", selectSrc.value);
    updateVocabDetails("target-details", selectTgt.value);
    runPathfinder();
  });

  // Preset chips
  document.querySelectorAll(".chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const src = chip.getAttribute("data-src");
      const tgt = chip.getAttribute("data-tgt");
      if (src && selectSrc.querySelector(`option[value='${src}']`)) selectSrc.value = src;
      if (tgt && selectTgt.querySelector(`option[value='${tgt}']`)) selectTgt.value = tgt;
      updateVocabDetails("source-details", selectSrc.value);
      updateVocabDetails("target-details", selectTgt.value);
      runPathfinder();
    });
  });

  btnFind.addEventListener("click", runPathfinder);

  const btnCopyPath = document.getElementById("btn-copy-path");
  if (btnCopyPath) {
    btnCopyPath.addEventListener("click", () => {
      const title = document.getElementById("path-summary-title")?.textContent || "";
      const narrative = document.getElementById("path-narrative-text")?.innerText || "";
      if (navigator.clipboard && (title || narrative)) {
        navigator.clipboard.writeText(`${title}\n\n${narrative}`).then(() => {
          const orig = btnCopyPath.textContent;
          btnCopyPath.textContent = "Copied!";
          setTimeout(() => { btnCopyPath.textContent = orig; }, 1800);
        });
      }
    });
  }

  // Auto-run first search
  setTimeout(runPathfinder, 200);
}

function updateVocabDetails(containerId, prefix) {
  const container = document.getElementById(containerId);
  if (!container || !prefix) return;
  const ep = ENDPOINT_MAP.get(prefix.toLowerCase());
  if (ep) {
    container.innerHTML = `<strong>${ep.name}</strong> &bull; Authority: <em>${ep.authority}</em> &bull; URI: <code class="curie-code">${ep.uri_prefix}</code>`;
  } else {
    container.innerHTML = `<strong>${prefix.toUpperCase()}</strong> &bull; Mapping Commons Registered Endpoint`;
  }
}

/**
 * Finds shortest multi-hop path using Breadth-First-Search (BFS)
 */
function findShortestPathBFS(startPrefix, endPrefix) {
  startPrefix = startPrefix.toLowerCase();
  endPrefix = endPrefix.toLowerCase();

  if (startPrefix === endPrefix) {
    return { path: [startPrefix], hops: [] };
  }

  const queue = [[startPrefix]];
  const visited = new Set([startPrefix]);
  const parentEdge = new Map(); // child -> edge to child

  while (queue.length > 0) {
    const currentPath = queue.shift();
    const currNode = currentPath[currentPath.length - 1];

    if (currNode === endPrefix) {
      // Reconstruct hop edge details
      const hops = [];
      for (let i = 0; i < currentPath.length - 1; i++) {
        const u = currentPath[i];
        const v = currentPath[i + 1];
        // find edge info
        const neighbors = ADJACENCY[u] || [];
        const edge = neighbors.find(n => n.neighbor.toLowerCase() === v.toLowerCase());
        hops.push({
          from: u,
          to: v,
          edgeInfo: edge || { count: 0, predicates: { "skos:exactMatch": 1 }, file: `commons/${u}/${v}/${u}_${v}.sssom.tsv` }
        });
      }
      return { path: currentPath, hops };
    }

    const neighbors = ADJACENCY[currNode] || [];
    for (const edge of neighbors) {
      const neighbor = edge.neighbor.toLowerCase();
      if (!visited.has(neighbor)) {
        visited.add(neighbor);
        queue.push([...currentPath, neighbor]);
      }
    }
  }

  return null; // No path found
}

function runPathfinder() {
  const src = document.getElementById("select-source-vocab").value;
  const tgt = document.getElementById("select-target-vocab").value;
  const resultCard = document.getElementById("path-results-card");
  const badgeHops = document.getElementById("path-badge-hops");
  const titleEl = document.getElementById("path-summary-title");
  const timelineEl = document.getElementById("path-timeline");
  const narrativeEl = document.getElementById("path-narrative-text");
  const tbodySamples = document.getElementById("tbody-path-samples");

  if (!src || !tgt) return;

  const result = findShortestPathBFS(src, tgt);

  resultCard.style.display = "block";
  timelineEl.innerHTML = "";
  tbodySamples.innerHTML = "";

  if (!result) {
    badgeHops.className = "badge-status";
    badgeHops.style.backgroundColor = "rgba(244, 63, 94, 0.2)";
    badgeHops.style.color = "var(--accent-rose)";
    badgeHops.textContent = "No Path Discovered";
    titleEl.textContent = `No Crosswalk Bridge Found Between ${src.toUpperCase()} and ${tgt.toUpperCase()}`;
    narrativeEl.innerHTML = `No transitive path exists between <strong>${src.toUpperCase()}</strong> and <strong>${tgt.toUpperCase()}</strong> in the current repository graph. To connect them, contribute a direct pairwise mapping or bridge them via an upper ontology (such as BFO or MeSH).`;
    return;
  }

  const hopCount = result.hops.length;
  if (hopCount === 1) {
    badgeHops.className = "badge-status";
    badgeHops.style.backgroundColor = "rgba(16, 185, 129, 0.2)";
    badgeHops.style.color = "var(--accent-emerald)";
    badgeHops.textContent = "Direct Mapping (1 Hop)";
  } else {
    badgeHops.className = "badge-status multi-hop";
    badgeHops.textContent = `Transitive Bridge (${hopCount} Hops)`;
  }

  titleEl.textContent = `${src.toUpperCase()} \u2192 ${tgt.toUpperCase()} Crosswalk Path`;

  // 1. Build Visual Timeline
  result.path.forEach((nodePrefix, idx) => {
    const ep = ENDPOINT_MAP.get(nodePrefix) || { name: nodePrefix.toUpperCase(), authority: "Registry" };
    const stepDiv = document.createElement("div");
    stepDiv.className = "timeline-step";

    stepDiv.innerHTML = `
      <div class="timeline-node">
        <div class="timeline-node-prefix">${nodePrefix}</div>
        <div class="timeline-node-title">${ep.name}</div>
        <div class="timeline-node-auth">${ep.authority}</div>
      </div>
    `;

    timelineEl.appendChild(stepDiv);

    // If there is an edge to next node
    if (idx < result.hops.length) {
      const hop = result.hops[idx];
      const edge = hop.edgeInfo;
      const preds = edge.predicates ? Object.keys(edge.predicates) : ["skos:exactMatch"];
      const primaryPred = preds[0] || "skos:exactMatch";

      const edgeDiv = document.createElement("div");
      edgeDiv.className = "timeline-edge";
      edgeDiv.innerHTML = `
        <span class="edge-pill">${primaryPred.replace("skos:", "").replace("rdfs:", "")}</span>
        <div class="edge-arrow" title="${edge.count ? edge.count.toLocaleString() + ' mappings' : ''}"></div>
        <span style="font-size: 0.72rem; color: var(--text-dim);">${edge.count ? edge.count.toLocaleString() + ' rows' : ''}</span>
      `;
      timelineEl.appendChild(edgeDiv);
    }
  });

  // 2. Build Narrative Explanation
  const repoBlobBase = "https://github.com/Superraptor/KOS-Mappings/blob/main/";
  let narrative = "";
  if (hopCount === 1) {
    const hop = result.hops[0];
    const cnt = hop.edgeInfo.count ? hop.edgeInfo.count.toLocaleString() : "many";
    const srcName = ENDPOINT_MAP.get(src)?.name || src.toUpperCase();
    const tgtName = ENDPOINT_MAP.get(tgt)?.name || tgt.toUpperCase();
    narrative = `A <strong>direct canonical mapping set</strong> connects <strong>${srcName} (${src.toUpperCase()})</strong> to <strong>${tgtName} (${tgt.toUpperCase()})</strong> with <strong>${cnt}</strong> curated alignment rows. This crosswalk is published in <a href="${repoBlobBase}${hop.edgeInfo.file}" target="_blank" rel="noopener noreferrer" style="color: var(--accent-cyan); font-family: var(--font-mono);">${hop.edgeInfo.file}</a>.`;
  } else {
    const srcName = ENDPOINT_MAP.get(src)?.name || src.toUpperCase();
    const tgtName = ENDPOINT_MAP.get(tgt)?.name || tgt.toUpperCase();
    narrative = `No single direct file links <strong>${srcName}</strong> directly to <strong>${tgtName}</strong>. Instead, our semantic pathfinder discovered a <strong>${hopCount}-hop bridging crosswalk</strong>:<br><br>`;
    
    result.hops.forEach((h, i) => {
      const uName = ENDPOINT_MAP.get(h.from)?.name || h.from.toUpperCase();
      const vName = ENDPOINT_MAP.get(h.to)?.name || h.to.toUpperCase();
      const pred = Object.keys(h.edgeInfo.predicates || {})[0] || "skos:exactMatch";
      narrative += `&bull; <strong>Hop ${i + 1}</strong>: <em>${uName}</em> &rarr; <em>${vName}</em> using predicate <code>${pred}</code> (${(h.edgeInfo.count || 0).toLocaleString()} alignments in <a href="${repoBlobBase}${h.edgeInfo.file}" target="_blank" rel="noopener noreferrer" style="color: var(--accent-cyan); font-family: var(--font-mono);">${h.edgeInfo.file}</a>)<br>`;
    });

    narrative += `<br>This allows transitive query expansion and interoperability between entities in both systems by chaining through the intermediate hubs.`;
  }
  narrativeEl.innerHTML = narrative;

  // 3. Populate Concrete Sample Mappings on Path
  let sampleCount = 0;
  result.hops.forEach((h, hopIdx) => {
    const samples = h.edgeInfo.samples || [];
    samples.slice(0, 3).forEach(s => {
      sampleCount++;
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><span class="badge-pill">Hop ${hopIdx + 1}</span></td>
        <td>
          <span class="curie-code">${s.subject_id}</span>
          <div style="font-size: 0.82rem; margin-top: 0.2rem;">${s.subject_label || ''}</div>
        </td>
        <td><span class="badge-predicate ${getPredicateClass(s.predicate_id)}">${s.predicate_id}</span></td>
        <td>
          <span class="curie-code">${s.object_id}</span>
          <div style="font-size: 0.82rem; margin-top: 0.2rem;">${s.object_label || ''}</div>
        </td>
        <td style="font-size: 0.8rem; color: var(--text-dim);">${s.mapping_justification ? s.mapping_justification.replace('semapv:', '') : 'Curated'}</td>
      `;
      tbodySamples.appendChild(tr);
    });
  });

  if (sampleCount === 0) {
    tbodySamples.innerHTML = `<tr><td colspan="5" class="empty-state">No individual sample rows cached for this edge. Refer to file path.</td></tr>`;
  }
}

function getPredicateClass(pred) {
  if (!pred) return "";
  const p = pred.toLowerCase();
  if (p.includes("exact")) return "exact";
  if (p.includes("broad")) return "broad";
  if (p.includes("narrow")) return "narrow";
  if (p.includes("close")) return "close";
  return "";
}

// --------------------------------------------------------------------------
// 4. Concept & Mapping Query Engine
// --------------------------------------------------------------------------
function setupQueryEngine() {
  const inputSearch = document.getElementById("input-global-search");
  const btnClear = document.getElementById("btn-clear-search");
  const filterPred = document.getElementById("filter-predicate");
  const filterSrc = document.getElementById("filter-source");
  const filterTgt = document.getElementById("filter-target");
  const tbody = document.getElementById("tbody-query-results");
  const countBadge = document.getElementById("query-count-badge");

  if (!GRAPH_DATA) return;

  // Populate source/target filters
  const sortedNodes = [...GRAPH_DATA.nodes].sort((a, b) => a.id.localeCompare(b.id));
  sortedNodes.forEach(n => {
    const optS = document.createElement("option");
    optS.value = n.id;
    optS.textContent = `${n.id} (${n.name})`;
    filterSrc.appendChild(optS);

    const optT = document.createElement("option");
    optT.value = n.id;
    optT.textContent = `${n.id} (${n.name})`;
    filterTgt.appendChild(optT);
  });

  function renderQueryResults() {
    const q = inputSearch.value.toLowerCase().trim();
    const selPred = filterPred.value;
    const selSrc = filterSrc.value;
    const selTgt = filterTgt.value;

    btnClear.style.display = q ? "block" : "none";

    const samples = GRAPH_DATA.search_samples || [];
    const filtered = samples.filter(m => {
      if (selPred && m.predicate_id !== selPred) return false;
      if (selSrc && m.source !== selSrc) return false;
      if (selTgt && m.target !== selTgt) return false;

      if (!q) return true;
      return (
        m.subject_id.toLowerCase().includes(q) ||
        (m.subject_label && m.subject_label.toLowerCase().includes(q)) ||
        m.object_id.toLowerCase().includes(q) ||
        (m.object_label && m.object_label.toLowerCase().includes(q)) ||
        m.source.includes(q) ||
        m.target.includes(q)
      );
    });

    countBadge.textContent = `Showing ${filtered.length} matching mappings`;
    tbody.innerHTML = "";

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="empty-state" style="text-align: center; padding: 2rem; color: var(--text-dim);">No mappings match the active filters. Try searching for "cholesterol", "estradiol", "unit", or "heart".</td></tr>`;
      return;
    }

    filtered.slice(0, 50).forEach(m => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><span class="curie-code">${m.subject_id}</span></td>
        <td><strong>${m.subject_label || '-'}</strong></td>
        <td><span class="badge-predicate ${getPredicateClass(m.predicate_id)}">${m.predicate_id}</span></td>
        <td><span class="curie-code">${m.object_id}</span></td>
        <td><strong>${m.object_label || '-'}</strong></td>
        <td style="font-size: 0.8rem; color: var(--text-dim);">${(m.mapping_justification || '').replace('semapv:', '')}</td>
        <td><span class="badge-pill">${m.source} &rarr; ${m.target}</span></td>
      `;
      tbody.appendChild(tr);
    });
  }

  inputSearch.addEventListener("input", renderQueryResults);
  btnClear.addEventListener("click", () => {
    inputSearch.value = "";
    renderQueryResults();
  });
  filterPred.addEventListener("change", renderQueryResults);
  filterSrc.addEventListener("change", renderQueryResults);
  filterTgt.addEventListener("change", renderQueryResults);

  renderQueryResults();
}

// --------------------------------------------------------------------------
// 5. Endpoints Directory View
// --------------------------------------------------------------------------
function setupEndpointsView() {
  const grid = document.getElementById("endpoints-grid");
  const filterInput = document.getElementById("input-endpoint-filter");
  const catPills = document.querySelectorAll(".cat-pill");

  let activeCategory = "ALL";

  function renderGrid() {
    const q = filterInput.value.toLowerCase().trim();
    grid.innerHTML = "";

    const filtered = ENDPOINTS.filter(ep => {
      if (activeCategory !== "ALL" && ep.category !== activeCategory) return false;
      if (!q) return true;
      return (
        ep.prefix.toLowerCase().includes(q) ||
        ep.name.toLowerCase().includes(q) ||
        ep.authority.toLowerCase().includes(q) ||
        ep.description.toLowerCase().includes(q)
      );
    });

    filtered.forEach(ep => {
      const card = document.createElement("div");
      card.className = "endpoint-card";
      card.innerHTML = `
        <div>
          <div class="endpoint-head">
            <span class="endpoint-prefix">${ep.prefix}</span>
            <span class="badge-cat">${ep.category}</span>
          </div>
          <div class="endpoint-name">${ep.name}</div>
          <p class="endpoint-desc">${ep.description}</p>
        </div>
        <div class="endpoint-footer">
          <span>${ep.authority}</span>
          <span class="endpoint-uri" title="${ep.uri_prefix}">${ep.uri_prefix}</span>
        </div>
      `;
      grid.appendChild(card);
    });
  }

  filterInput.addEventListener("input", renderGrid);

  catPills.forEach(pill => {
    pill.addEventListener("click", () => {
      catPills.forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      activeCategory = pill.getAttribute("data-category");
      renderGrid();
    });
  });

  renderGrid();
}

// --------------------------------------------------------------------------
// 6. Topology & Metrics View
// --------------------------------------------------------------------------
function setupTopologyView() {
  if (!GRAPH_DATA || !GRAPH_DATA.stats) return;

  document.getElementById("stat-total-vocabs").textContent = GRAPH_DATA.stats.total_vocabularies.toLocaleString();
  document.getElementById("stat-total-edges").textContent = GRAPH_DATA.stats.total_mapping_sets.toLocaleString();
  document.getElementById("stat-total-mappings").textContent = GRAPH_DATA.stats.total_mappings.toLocaleString();

  // Top Hubs
  const hubsContainer = document.getElementById("top-hubs-container");
  const topHubs = [...GRAPH_DATA.nodes].sort((a, b) => b.degree - a.degree).slice(0, 8);

  hubsContainer.innerHTML = "";
  topHubs.forEach(hub => {
    const div = document.createElement("div");
    div.className = "hub-card";
    div.innerHTML = `
      <div class="hub-info">
        <h5>${hub.id.toUpperCase()} - ${hub.name}</h5>
        <span>${hub.mapping_count.toLocaleString()} mappings &bull; ${hub.authority}</span>
      </div>
      <div class="hub-badge" title="Degree / Connected Vocabularies">${hub.degree} connections</div>
    `;
    hubsContainer.appendChild(div);
  });

  // Full Edges Table
  const tbodyEdges = document.getElementById("tbody-all-edges");
  tbodyEdges.innerHTML = "";
  const sortedEdges = [...GRAPH_DATA.edges].sort((a, b) => b.count - a.count);

  const repoBlobBase = "https://github.com/Superraptor/KOS-Mappings/blob/main/";
  sortedEdges.slice(0, 100).forEach(edge => {
    const tr = document.createElement("tr");
    const domPred = Object.keys(edge.predicates || {})[0] || "skos:exactMatch";
    tr.innerHTML = `
      <td><span class="curie-code">${edge.source}</span></td>
      <td><span class="curie-code">${edge.target}</span></td>
      <td><strong>${edge.count.toLocaleString()}</strong></td>
      <td><span class="badge-predicate ${getPredicateClass(domPred)}">${domPred}</span></td>
      <td><a href="${repoBlobBase}${edge.file}" target="_blank" rel="noopener noreferrer" style="color: var(--accent-cyan); font-family: var(--font-mono); font-size: 0.8rem;">${edge.file}</a></td>
      <td style="font-size: 0.78rem; color: var(--text-dim);">${edge.license}</td>
    `;
    tbodyEdges.appendChild(tr);
  });
}
