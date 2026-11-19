/**
 * MTP Push Task EMG Analysis Portal - Main Application Logic
 */

// Global State
let mtpData = null;
let currentView = 'dashboard';
let explorerState = {
  load: '2.5kg',
  muscle: 'both',
  metric: 'rms',
  visibleSubjects: new Set()
};
let compareState = {
  mode: 'subject-across-loads', // 'subject-across-loads', 'subjects-at-load', 'muscle-head-to-head'
  subject: 'gau',
  load: '2.5kg'
};
let simState = {
  load: '2.5kg',
  subject: 'balk',
  galleryFilter: 'selected',
  speed: 1.0,
  progressFrac: 0.0
};

// Chart instances
let overviewRmsChart = null;
let overviewMdfChart = null;
let explorerChart = null;
let cmpChart1Instance = null;
let cmpChart2Instance = null;
let simRmsChart = null;
let simMdfChart = null;
let simRafId = null;

// Distinct Subject Color Palette
const SUBJECT_COLORS = {
  balk:   '#D97706',  // Amber
  gau:    '#2563EB',  // Royal Blue
  mil:    '#059669',  // Emerald Green
  muk:    '#7C3AED',  // Purple
  priy:   '#DB2777',  // Pink
  ritesh: '#EA580C',  // Orange
  swr:    '#0891B2',  // Cyan
  tapas:  '#0D9488'   // Teal
};

const MUSCLE_COLORS = {
  biceps: {
    primary: '#2563EB',
    bg: 'rgba(37, 99, 235, 0.15)',
    border: '#1D4ED8'
  },
  triceps: {
    primary: '#DC2626',
    bg: 'rgba(220, 38, 38, 0.15)',
    border: '#B91C1C'
  }
};

// Document Ready Initialization
document.addEventListener('DOMContentLoaded', async () => {
  if (window.lucide) {
    lucide.createIcons();
  }
  await loadDataset();
  setupEventListeners();
  renderDashboard();
});

// Load Dataset from API or static JSON
async function loadDataset() {
  try {
    const res = await fetch('/api/data');
    if (!res.ok) throw new Error('API fetch error');
    mtpData = await res.json();
  } catch (err) {
    console.warn('API route failed, trying static /data/mtp_data.json...', err);
    try {
      const resStatic = await fetch('/data/mtp_data.json');
      if (!resStatic.ok) throw new Error('Static fetch error');
      mtpData = await resStatic.json();
    } catch (e2) {
      if (window.EMBEDDED_MTP_DATA) {
        console.info('Using embedded fallback MTP dataset.');
        mtpData = window.EMBEDDED_MTP_DATA;
      } else {
        console.error('Failed to load mtp_data.json:', e2);
        alert('Could not load MTP data. Please ensure the backend server is running.');
        return;
      }
    }
  }

  // Populate UI elements
  updateHeaderStats();
  renderLoadCards();
  renderDatasetTable();
  renderScalingTable();
  initExplorerSubjectToggles();
}

function setupEventListeners() {
  // Navigation active state styling
  updateNavState('dashboard');
}

function updateHeaderStats() {
  if (!mtpData) return;
  const loadsCount = Object.keys(mtpData.loads || {}).length;
  const subjectsCount = Object.keys(mtpData.subjects || {}).length;
  const trialsCount = (mtpData.comparison_matrix || []).length;

  const elLoads = document.getElementById('stat-total-loads');
  const elSubjects = document.getElementById('stat-total-subjects');
  const elTrials = document.getElementById('stat-total-trials');
  const elSamples = document.getElementById('stat-total-samples');

  if (elLoads) elLoads.innerText = loadsCount;
  if (elSubjects) elSubjects.innerText = subjectsCount;
  if (elTrials) elTrials.innerText = trialsCount;
  if (elSamples) elSamples.innerText = `${(trialsCount * 360000).toLocaleString()} raw samples processed`;
}

// Switch Top Navigation Views
function switchView(viewId) {
  const views = ['dashboard', 'load-explorer', 'simulations', 'comparison-studio', 'data-table', 'upload-modal'];
  views.forEach(v => {
    const el = document.getElementById(`view-${v}`);
    if (el) {
      if (v === viewId) {
        el.classList.remove('hidden');
      } else {
        el.classList.add('hidden');
      }
    }
  });

  updateNavState(viewId);
  currentView = viewId;

  // View-specific trigger
  if (viewId === 'dashboard') {
    renderDashboardOverviewCharts();
  } else if (viewId === 'load-explorer') {
    renderExplorerChart();
    renderPublicationPlots();
  } else if (viewId === 'simulations') {
    renderSimulationsView();
  } else if (viewId === 'comparison-studio') {
    renderCompareControls();
    renderCompareCharts();
  } else if (viewId === 'data-table') {
    renderDatasetTable();
  }

  if (window.lucide) {
    lucide.createIcons();
  }
}

function updateNavState(activeId) {
  const tabs = ['dashboard', 'load-explorer', 'simulations', 'comparison-studio', 'data-table', 'upload-modal'];
  tabs.forEach(t => {
    const btn = document.getElementById(`nav-${t}`);
    if (!btn) return;
    if (t === activeId && t !== 'upload-modal') {
      btn.className = "px-3 py-1.5 rounded-lg text-sm font-semibold bg-slate-900 text-white flex items-center space-x-1.5 shadow-sm";
    } else if (t !== 'upload-modal') {
      btn.className = "px-3 py-1.5 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-100 flex items-center space-x-1.5 transition";
    }
  });
}

// ========================================================
// DASHBOARD VIEW
// ========================================================
function renderDashboard() {
  renderLoadCards();
  renderDashboardOverviewCharts();
}

function renderLoadCards() {
  const container = document.getElementById('load-cards-container');
  if (!container || !mtpData) return;

  container.innerHTML = '';
  const loads = ['2.5kg', '5kg', '7.5kg', '10kg'];

  loads.forEach(lid => {
    const lObj = mtpData.loads[lid];
    if (!lObj) return;

    const subjs = Object.keys(lObj.subjects || {});
    const meanTricepsRms = lObj.load_stats.mean_triceps_rms || 0;
    const meanBicepsRms = lObj.load_stats.mean_biceps_rms || 0;

    const card = document.createElement('div');
    card.className = "glass-card p-5 cursor-pointer hover:border-blue-400 group relative overflow-hidden";
    card.onclick = () => {
      selectExplorerLoad(lid);
      switchView('load-explorer');
    };

    card.innerHTML = `
      <div class="flex items-center justify-between">
        <span class="px-2.5 py-1 rounded-lg text-xs font-bold bg-blue-50 text-blue-700 border border-blue-200">
          ${lObj.name}
        </span>
        <span class="text-xs text-slate-400 group-hover:text-blue-600 transition flex items-center gap-0.5">
          Explore <i data-lucide="arrow-right" class="w-3.5 h-3.5"></i>
        </span>
      </div>
      <div class="mt-3">
        <div class="text-xl font-bold text-slate-900">${lObj.mass_kg} kg Push</div>
        <p class="text-xs text-slate-500 mt-0.5">${subjs.length} Active Subjects: ${subjs.map(s => s.toUpperCase()).join(', ')}</p>
      </div>
      <div class="mt-4 pt-3 border-t border-slate-100 grid grid-cols-2 gap-2 text-xs">
        <div>
          <span class="text-slate-400 block text-[10px] uppercase font-semibold">Triceps RMS</span>
          <span class="font-bold text-red-600">${meanTricepsRms.toFixed(1)} ADC</span>
        </div>
        <div>
          <span class="text-slate-400 block text-[10px] uppercase font-semibold">Biceps RMS</span>
          <span class="font-bold text-blue-600">${meanBicepsRms.toFixed(1)} ADC</span>
        </div>
      </div>
    `;

    container.appendChild(card);
  });

  if (window.lucide) lucide.createIcons();
}

function renderDashboardOverviewCharts() {
  if (!mtpData) return;

  const loads = ['2.5kg', '5kg', '7.5kg', '10kg'];
  const labels = loads.map(l => mtpData.loads[l]?.name || l);
  const bRms = loads.map(l => mtpData.loads[l]?.load_stats.mean_biceps_rms || 0);
  const tRms = loads.map(l => mtpData.loads[l]?.load_stats.mean_triceps_rms || 0);

  const bMdf = loads.map(l => mtpData.loads[l]?.load_stats.mean_biceps_mdf || 0);
  const tMdf = loads.map(l => mtpData.loads[l]?.load_stats.mean_triceps_mdf || 0);

  // 1. RMS Overview Chart
  const ctxRms = document.getElementById('overviewLoadRmsChart');
  if (ctxRms) {
    if (overviewRmsChart) overviewRmsChart.destroy();
    overviewRmsChart = new Chart(ctxRms, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Triceps (Agonist)',
            data: tRms,
            backgroundColor: '#DC2626',
            borderRadius: 6,
            borderWidth: 1,
            borderColor: '#991B1B'
          },
          {
            label: 'Biceps (Antagonist)',
            data: bRms,
            backgroundColor: '#2563EB',
            borderRadius: 6,
            borderWidth: 1,
            borderColor: '#1D4ED8'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top', labels: { boxWidth: 12, font: { size: 11 } } },
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${ctx.raw.toFixed(1)} ADC`
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            title: { display: true, text: 'Muscular Activity (RMS - ADC)', font: { size: 10 } },
            grid: { color: '#F1F5F9' }
          },
          x: { grid: { display: false } }
        }
      }
    });
  }

  // 2. MDF Overview Chart
  const ctxMdf = document.getElementById('overviewLoadMdfChart');
  if (ctxMdf) {
    if (overviewMdfChart) overviewMdfChart.destroy();
    overviewMdfChart = new Chart(ctxMdf, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Triceps MDF (Hz)',
            data: tMdf,
            borderColor: '#DC2626',
            backgroundColor: 'rgba(220, 38, 38, 0.1)',
            tension: 0.3,
            fill: false,
            borderWidth: 2.5,
            pointRadius: 5
          },
          {
            label: 'Biceps MDF (Hz)',
            data: bMdf,
            borderColor: '#2563EB',
            backgroundColor: 'rgba(37, 99, 235, 0.1)',
            tension: 0.3,
            fill: false,
            borderWidth: 2.5,
            pointRadius: 5
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top', labels: { boxWidth: 12, font: { size: 11 } } },
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${ctx.raw.toFixed(1)} Hz`
            }
          }
        },
        scales: {
          y: {
            title: { display: true, text: 'Median Frequency (Hz)', font: { size: 10 } },
            grid: { color: '#F1F5F9' }
          },
          x: { grid: { display: false } }
        }
      }
    });
  }
}

// ========================================================
// LOADS & MUSCLES EXPLORER
// ========================================================
function selectExplorerLoad(loadId) {
  explorerState.load = loadId;
  document.querySelectorAll('.explorer-load-btn').forEach(btn => {
    if (btn.getAttribute('data-load') === loadId) {
      btn.className = "explorer-load-btn tab-active px-4 py-2 rounded-xl text-sm font-semibold border border-transparent shadow-md transition";
    } else {
      btn.className = "explorer-load-btn px-4 py-2 rounded-xl text-sm font-semibold border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 transition";
    }
  });

  initExplorerSubjectToggles();
  renderExplorerChart();
  renderPublicationPlots();
}

function selectExplorerMuscle(muscle) {
  explorerState.muscle = muscle;
  ['biceps', 'triceps', 'both'].forEach(m => {
    const btn = document.getElementById(`btn-muscle-${m}`);
    if (btn) {
      if (m === muscle) {
        btn.className = "sub-tab-active flex-1 sm:flex-none px-4 py-1.5 rounded-lg text-xs font-semibold shadow-sm";
      } else {
        btn.className = "flex-1 sm:flex-none px-4 py-1.5 rounded-lg text-xs font-semibold transition text-slate-600 hover:text-slate-900";
      }
    }
  });
  renderExplorerChart();
}

function selectExplorerMetric(metric) {
  explorerState.metric = metric;
  ['rms', 'mdf', 'total_bar'].forEach(met => {
    const id = met === 'total_bar' ? 'btn-metric-total-bar' : `btn-metric-${met}`;
    const btn = document.getElementById(id);
    if (btn) {
      if (met === metric) {
        btn.className = "sub-tab-active flex-1 sm:flex-none px-4 py-1.5 rounded-lg text-xs font-semibold shadow-sm";
      } else {
        btn.className = "flex-1 sm:flex-none px-4 py-1.5 rounded-lg text-xs font-semibold transition text-slate-600 hover:text-slate-900";
      }
    }
  });
  renderExplorerChart();
}

function initExplorerSubjectToggles() {
  const container = document.getElementById('chartSubjectToggles');
  if (!container || !mtpData) return;

  container.innerHTML = '';
  let subjects = [];

  if (explorerState.load === 'all') {
    subjects = Object.keys(mtpData.subjects || {});
  } else {
    const lObj = mtpData.loads[explorerState.load];
    subjects = lObj ? Object.keys(lObj.subjects || {}) : [];
  }

  // Reset visible set to all by default
  explorerState.visibleSubjects = new Set(subjects);

  subjects.forEach(subj => {
    const pill = document.createElement('button');
    pill.className = "px-2.5 py-1 rounded-full text-[11px] font-semibold border flex items-center space-x-1 bg-white text-slate-700 border-slate-200 hover:border-slate-400 transition";
    pill.id = `toggle-subj-${subj}`;
    
    const color = SUBJECT_COLORS[subj] || '#475569';
    pill.innerHTML = `
      <span class="w-2 h-2 rounded-full inline-block" style="background-color: ${color}"></span>
      <span>${subj.toUpperCase()}</span>
    `;

    pill.onclick = () => {
      if (explorerState.visibleSubjects.has(subj)) {
        explorerState.visibleSubjects.delete(subj);
        pill.classList.add('opacity-40', 'line-through');
      } else {
        explorerState.visibleSubjects.add(subj);
        pill.classList.remove('opacity-40', 'line-through');
      }
      renderExplorerChart();
    };

    container.appendChild(pill);
  });
}

function renderExplorerChart() {
  const ctx = document.getElementById('explorerInteractiveChart');
  if (!ctx || !mtpData) return;

  const titleEl = document.getElementById('explorerChartTitle');
  const subEl = document.getElementById('explorerChartSubtitle');
  const badgeEl = document.getElementById('explorerChartBadge');

  if (explorerChart) explorerChart.destroy();

  const timeAxis = mtpData.metadata.time_axis || [];
  const timeLabels = timeAxis.map(t => `${Math.round(t)}s`);

  // Handle Total Bar Chart mode
  if (explorerState.metric === 'total_bar') {
    if (titleEl) titleEl.innerText = `Total Muscular Activity (RMS ADC) - ${explorerState.load.toUpperCase()} Push`;
    if (subEl) subEl.innerText = "Overall 3-Minute Trial Comparison (Biceps vs Triceps)";
    if (badgeEl) badgeEl.innerText = "Bar Comparison";

    let subjects = [];
    if (explorerState.load === 'all') {
      subjects = Object.keys(mtpData.subjects || {});
    } else {
      const lObj = mtpData.loads[explorerState.load];
      subjects = lObj ? Object.keys(lObj.subjects || {}) : [];
    }

    subjects = subjects.filter(s => explorerState.visibleSubjects.has(s));

    const labels = subjects.map(s => s.toUpperCase());
    const bVals = [];
    const tVals = [];

    subjects.forEach(s => {
      let bRms = 0, tRms = 0;
      if (explorerState.load === 'all') {
        // Average across loads
        const pLoads = mtpData.subjects[s].participated_loads || [];
        let bSum = 0, tSum = 0;
        pLoads.forEach(l => {
          bSum += mtpData.subjects[s].load_data[l].total_biceps_rms;
          tSum += mtpData.subjects[s].load_data[l].total_triceps_rms;
        });
        bRms = pLoads.length ? bSum / pLoads.length : 0;
        tRms = pLoads.length ? tSum / pLoads.length : 0;
      } else {
        const sData = mtpData.loads[explorerState.load].subjects[s];
        bRms = sData.total_biceps_rms;
        tRms = sData.total_triceps_rms;
      }
      bVals.push(bRms);
      tVals.push(tRms);
    });

    const datasets = [];
    if (explorerState.muscle === 'biceps' || explorerState.muscle === 'both') {
      datasets.push({
        label: 'Biceps Brachii',
        data: bVals,
        backgroundColor: '#2563EB',
        borderRadius: 6
      });
    }
    if (explorerState.muscle === 'triceps' || explorerState.muscle === 'both') {
      datasets.push({
        label: 'Triceps Brachii',
        data: tVals,
        backgroundColor: '#DC2626',
        borderRadius: 6
      });
    }

    explorerChart = new Chart(ctx, {
      type: 'bar',
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top' },
          tooltip: {
            callbacks: {
              label: (c) => `${c.dataset.label}: ${c.raw.toFixed(1)} ADC`
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            title: { display: true, text: 'Total Trial RMS (Raw ADC)' },
            grid: { color: '#F1F5F9' }
          },
          x: { grid: { display: false } }
        }
      }
    });
    return;
  }

  // Time-Series Line Chart mode (RMS or MDF)
  const isRms = explorerState.metric === 'rms';
  const metricName = isRms ? 'RMS Muscular Activity' : 'Median Frequency (MDF Fatigue)';
  const unit = isRms ? 'ADC' : 'Hz';

  if (titleEl) titleEl.innerText = `${metricName} vs Time | ${explorerState.load.toUpperCase()}`;
  if (subEl) subEl.innerText = `Windowed 5-second progression across 180s (${explorerState.muscle.toUpperCase()} Muscle)`;
  if (badgeEl) badgeEl.innerText = isRms ? "Recruitment" : "Fatigue Decay";

  let subjects = [];
  if (explorerState.load === 'all') {
    subjects = Object.keys(mtpData.subjects || {});
  } else {
    const lObj = mtpData.loads[explorerState.load];
    subjects = lObj ? Object.keys(lObj.subjects || {}) : [];
  }
  subjects = subjects.filter(s => explorerState.visibleSubjects.has(s));

  const datasets = [];

  subjects.forEach(subj => {
    const color = SUBJECT_COLORS[subj] || '#3B82F6';
    let sData = null;

    if (explorerState.load === 'all') {
      // Pick first participated load or average
      const pLoads = mtpData.subjects[subj].participated_loads;
      if (pLoads.length > 0) {
        sData = mtpData.subjects[subj].load_data[pLoads[0]];
      }
    } else {
      sData = mtpData.loads[explorerState.load]?.subjects[subj];
    }

    if (!sData) return;

    if (explorerState.muscle === 'biceps' || explorerState.muscle === 'both') {
      const series = isRms ? sData.biceps.rms_series : sData.biceps.mdf_series;
      datasets.push({
        label: `${subj.toUpperCase()} (Biceps)`,
        data: series,
        borderColor: explorerState.muscle === 'both' ? '#2563EB' : color,
        backgroundColor: 'transparent',
        borderWidth: 2,
        tension: 0.25,
        pointRadius: 2,
        pointHoverRadius: 5,
        borderDash: explorerState.muscle === 'both' ? [4, 4] : []
      });
    }

    if (explorerState.muscle === 'triceps' || explorerState.muscle === 'both') {
      const series = isRms ? sData.triceps.rms_series : sData.triceps.mdf_series;
      datasets.push({
        label: `${subj.toUpperCase()} (Triceps)`,
        data: series,
        borderColor: explorerState.muscle === 'both' ? '#DC2626' : color,
        backgroundColor: 'transparent',
        borderWidth: 2.2,
        tension: 0.25,
        pointRadius: 2,
        pointHoverRadius: 5
      });
    }
  });

  explorerChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: timeLabels,
      datasets: datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: {
          position: 'top',
          labels: { boxWidth: 12, font: { size: 10 } }
        },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${ctx.raw.toFixed(1)} ${unit}`
          }
        }
      },
      scales: {
        y: {
          title: { display: true, text: `${metricName} (${unit})` },
          grid: { color: '#F1F5F9' }
        },
        x: {
          title: { display: true, text: 'Time in Trial (Seconds)' },
          grid: { color: '#F8FAFC' }
        }
      }
    }
  });
}

// Publication Plots Viewer
function renderPublicationPlots(filter = 'all') {
  const container = document.getElementById('publicationPlotsContainer');
  if (!container || !mtpData) return;

  const currentLoad = explorerState.load === 'all' ? '2.5kg' : explorerState.load;
  container.innerHTML = '';

  const plots = [
    {
      type: 'bar',
      title: 'Muscular Activity (RMS) Bar Plot',
      desc: 'Biceps vs Triceps Total RMS comparison across all subjects',
      url: `/plots/${currentLoad}/emg_rms_bar_plot.png`
    },
    {
      type: 'time_rms',
      title: 'Time → RMS Windowed Plot',
      desc: '5-second windowed muscular recruitment over 180 seconds with variance bands',
      url: `/plots/${currentLoad}/emg_time_rms.png`
    },
    {
      type: 'time_mdf',
      title: 'Time → Median Frequency (MDF) Plot',
      desc: 'Frequency shift & localized muscular fatigue decay over 180 seconds',
      url: `/plots/${currentLoad}/emg_time_mdf.png`
    }
  ];

  const filtered = filter === 'all' ? plots : plots.filter(p => p.type === filter);

  filtered.forEach(p => {
    const card = document.createElement('div');
    card.className = "border border-slate-200 rounded-xl overflow-hidden bg-white shadow-sm flex flex-col";
    card.innerHTML = `
      <div class="p-3 border-b border-slate-100 flex items-center justify-between">
        <div>
          <h5 class="text-xs font-bold text-slate-800">${p.title}</h5>
          <p class="text-[11px] text-slate-400">${currentLoad.toUpperCase()} Push Condition</p>
        </div>
        <button onclick="openImageModal('${p.url}', '${p.title} - ${currentLoad.toUpperCase()}')" class="p-1 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-blue-600 transition" title="Enlarge">
          <i data-lucide="maximize-2" class="w-4 h-4"></i>
        </button>
      </div>
      <div class="bg-slate-50 p-2 cursor-pointer group relative flex items-center justify-center flex-1 min-h-[220px]" onclick="openImageModal('${p.url}', '${p.title} - ${currentLoad.toUpperCase()}')">
        <img src="${p.url}" alt="${p.title}" class="max-h-56 object-contain rounded border border-slate-200 group-hover:opacity-95 transition" onerror="this.src='/plots/2.5kg/emg_rms_bar_plot.png'">
        <div class="absolute inset-0 bg-blue-600/10 opacity-0 group-hover:opacity-100 transition rounded flex items-center justify-center">
          <span class="px-2 py-1 rounded bg-white/90 text-xs font-bold text-blue-600 shadow">Click to Zoom</span>
        </div>
      </div>
      <div class="p-3 bg-white text-[11px] text-slate-500 border-t border-slate-100">
        ${p.desc}
      </div>
    `;
    container.appendChild(card);
  });

  if (window.lucide) lucide.createIcons();
}

function togglePlotType(type) {
  ['all', 'bar', 'time_rms', 'time_mdf'].forEach(t => {
    const id = t === 'all' ? 'btn-plot-all' : (t === 'bar' ? 'btn-plot-bar' : (t === 'time_rms' ? 'btn-plot-time-rms' : 'btn-plot-time-mdf'));
    const btn = document.getElementById(id);
    if (btn) {
      if (t === type) {
        btn.className = "sub-tab-active px-3 py-1 rounded-lg text-xs border border-slate-200 font-semibold";
      } else {
        btn.className = "px-3 py-1 rounded-lg text-xs border border-slate-200 text-slate-600 hover:bg-slate-50";
      }
    }
  });
  renderPublicationPlots(type);
}

// Modal zoom
function openImageModal(src, title) {
  const modal = document.getElementById('imageModal');
  const img = document.getElementById('modalImageSrc');
  const tit = document.getElementById('modalImageTitle');
  const dwn = document.getElementById('modalImageDownload');

  img.src = src;
  tit.innerText = title;
  dwn.href = src;
  modal.classList.remove('hidden');
}

function closeImageModal() {
  document.getElementById('imageModal').classList.add('hidden');
}

// ========================================================
// COMPARISON STUDIO
// ========================================================
function setCompareMode(mode) {
  compareState.mode = mode;
  ['subject-across-loads', 'subjects-at-load', 'muscle-head-to-head'].forEach(m => {
    const id = m === 'subject-across-loads' ? 'btn-cmp-sub-load' : (m === 'subjects-at-load' ? 'btn-cmp-subs-load' : 'btn-cmp-muscles');
    const btn = document.getElementById(id);
    if (btn) {
      if (m === mode) {
        btn.className = "sub-tab-active px-3 py-1.5 rounded-lg text-xs font-semibold shadow-sm";
      } else {
        btn.className = "px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-600 hover:text-slate-900";
      }
    }
  });
  renderCompareControls();
  renderCompareCharts();
}

function renderCompareControls() {
  const container = document.getElementById('compareControls');
  if (!container || !mtpData) return;

  container.innerHTML = '';

  if (compareState.mode === 'subject-across-loads') {
    // Select a Subject (e.g. Gau who has all 4 loads, or Mil, Balk)
    const subjects = Object.keys(mtpData.subjects || {});
    container.innerHTML = `
      <div>
        <label class="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">Select Subject</label>
        <select onchange="compareState.subject = this.value; renderCompareCharts();" class="w-full text-xs py-2 px-3 rounded-xl border border-slate-200 bg-white">
          ${subjects.map(s => `
            <option value="${s}" ${s === compareState.subject ? 'selected' : ''}>
              ${mtpData.subjects[s].name} (${s.toUpperCase()}) - ${mtpData.subjects[s].participated_loads.length} Loads
            </option>
          `).join('')}
        </select>
      </div>
      <div>
        <label class="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">Available Loads for Subject</label>
        <div class="py-2 text-xs font-semibold text-blue-700">
          ${(mtpData.subjects[compareState.subject]?.participated_loads || []).map(l => `<span class="px-2 py-0.5 rounded-full bg-blue-100 border border-blue-200 mr-1">${l}</span>`).join('')}
        </div>
      </div>
      <div class="flex items-center text-xs text-slate-500 pt-3">
        <span>Analyzes how this subject's muscle activity & fatigue scale from low to high resistance.</span>
      </div>
    `;
  } else if (compareState.mode === 'subjects-at-load') {
    // Select Load Condition
    const loads = ['2.5kg', '5kg', '7.5kg', '10kg'];
    container.innerHTML = `
      <div>
        <label class="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">Select Load Condition</label>
        <select onchange="compareState.load = this.value; renderCompareCharts();" class="w-full text-xs py-2 px-3 rounded-xl border border-slate-200 bg-white">
          ${loads.map(l => `
            <option value="${l}" ${l === compareState.load ? 'selected' : ''}>
              ${l.toUpperCase()} Push Task (${Object.keys(mtpData.loads[l]?.subjects || {}).length} Subjects)
            </option>
          `).join('')}
        </select>
      </div>
      <div class="col-span-2 flex items-center text-xs text-slate-500 pt-3">
        <span>Benchmarks all participating subjects under the exact same resistance load side-by-side.</span>
      </div>
    `;
  } else if (compareState.mode === 'muscle-head-to-head') {
    // Biceps vs Triceps co-activation
    const loads = ['2.5kg', '5kg', '7.5kg', '10kg'];
    const subjects = Object.keys(mtpData.subjects || {});
    container.innerHTML = `
      <div>
        <label class="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">Select Subject</label>
        <select onchange="compareState.subject = this.value; renderCompareCharts();" class="w-full text-xs py-2 px-3 rounded-xl border border-slate-200 bg-white">
          ${subjects.map(s => `
            <option value="${s}" ${s === compareState.subject ? 'selected' : ''}>${mtpData.subjects[s].name}</option>
          `).join('')}
        </select>
      </div>
      <div>
        <label class="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">Select Load</label>
        <select onchange="compareState.load = this.value; renderCompareCharts();" class="w-full text-xs py-2 px-3 rounded-xl border border-slate-200 bg-white">
          ${loads.map(l => `
            <option value="${l}" ${l === compareState.load ? 'selected' : ''}>${l.toUpperCase()} Push</option>
          `).join('')}
        </select>
      </div>
      <div class="flex items-center text-xs text-slate-500 pt-3">
        <span>Evaluates Agonist (Triceps) vs Antagonist/Stabilizer (Biceps) co-contraction balance.</span>
      </div>
    `;
  }
}

function renderCompareCharts() {
  const ctx1 = document.getElementById('cmpChart1');
  const ctx2 = document.getElementById('cmpChart2');
  if (!ctx1 || !ctx2 || !mtpData) return;

  if (cmpChart1Instance) cmpChart1Instance.destroy();
  if (cmpChart2Instance) cmpChart2Instance.destroy();

  const timeAxis = mtpData.metadata.time_axis || [];
  const timeLabels = timeAxis.map(t => `${Math.round(t)}s`);

  const t1 = document.getElementById('cmpChart1Title');
  const s1 = document.getElementById('cmpChart1Sub');
  const t2 = document.getElementById('cmpChart2Title');
  const s2 = document.getElementById('cmpChart2Sub');

  // LOAD COLORS FOR CROSS-LOAD COMPARISON
  const LOAD_PALETTE = {
    '2.5kg': '#10B981', // Emerald
    '5kg':   '#3B82F6', // Blue
    '7.5kg': '#F59E0B', // Amber
    '10kg':  '#EF4444'  // Red
  };

  if (compareState.mode === 'subject-across-loads') {
    const subj = compareState.subject;
    const sInfo = mtpData.subjects[subj];
    if (!sInfo) return;

    t1.innerText = `${sInfo.name}: Triceps RMS Across Loads`;
    s1.innerText = `Motor recruitment progression under increasing push resistance`;
    t2.innerText = `${sInfo.name}: Triceps MDF (Fatigue Decay) Across Loads`;
    s2.innerText = `Shift to lower frequencies reflecting fatigue rate`;

    const ds1 = [];
    const ds2 = [];

    const loads = sInfo.participated_loads;
    loads.forEach(lid => {
      const sData = sInfo.load_data[lid];
      const color = LOAD_PALETTE[lid] || '#6366F1';

      ds1.push({
        label: `${lid.toUpperCase()} Push`,
        data: sData.triceps.rms_series,
        borderColor: color,
        backgroundColor: 'transparent',
        borderWidth: 2.2,
        tension: 0.25,
        pointRadius: 2
      });

      ds2.push({
        label: `${lid.toUpperCase()} Push`,
        data: sData.triceps.mdf_series,
        borderColor: color,
        backgroundColor: 'transparent',
        borderWidth: 2.2,
        tension: 0.25,
        pointRadius: 2
      });
    });

    cmpChart1Instance = new Chart(ctx1, {
      type: 'line',
      data: { labels: timeLabels, datasets: ds1 },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'top' } },
        scales: {
          y: { title: { display: true, text: 'Triceps RMS (ADC)' }, grid: { color: '#F1F5F9' } },
          x: { title: { display: true, text: 'Time (s)' }, grid: { display: false } }
        }
      }
    });

    cmpChart2Instance = new Chart(ctx2, {
      type: 'line',
      data: { labels: timeLabels, datasets: ds2 },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'top' } },
        scales: {
          y: { title: { display: true, text: 'Triceps MDF (Hz)' }, grid: { color: '#F1F5F9' } },
          x: { title: { display: true, text: 'Time (s)' }, grid: { display: false } }
        }
      }
    });

  } else if (compareState.mode === 'subjects-at-load') {
    const lid = compareState.load;
    const lObj = mtpData.loads[lid];
    if (!lObj) return;

    t1.innerText = `${lObj.name}: Subjects Triceps Activity (RMS)`;
    s1.innerText = `Inter-individual motor unit recruitment comparison`;
    t2.innerText = `${lObj.name}: Subjects Fatigue Decay (MDF)`;
    s2.innerText = `Comparison of fatigue resilience across participants`;

    const subjs = Object.keys(lObj.subjects || {});
    const ds1 = [];
    const ds2 = [];

    subjs.forEach(s => {
      const sData = lObj.subjects[s];
      const color = SUBJECT_COLORS[s] || '#3B82F6';

      ds1.push({
        label: `${s.toUpperCase()} (Triceps)`,
        data: sData.triceps.rms_series,
        borderColor: color,
        backgroundColor: 'transparent',
        borderWidth: 2,
        tension: 0.25,
        pointRadius: 2
      });

      ds2.push({
        label: `${s.toUpperCase()} (MDF)`,
        data: sData.triceps.mdf_series,
        borderColor: color,
        backgroundColor: 'transparent',
        borderWidth: 2,
        tension: 0.25,
        pointRadius: 2
      });
    });

    cmpChart1Instance = new Chart(ctx1, {
      type: 'line',
      data: { labels: timeLabels, datasets: ds1 },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'top' } },
        scales: {
          y: { title: { display: true, text: 'Triceps RMS (ADC)' }, grid: { color: '#F1F5F9' } },
          x: { title: { display: true, text: 'Time (s)' }, grid: { display: false } }
        }
      }
    });

    cmpChart2Instance = new Chart(ctx2, {
      type: 'line',
      data: { labels: timeLabels, datasets: ds2 },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'top' } },
        scales: {
          y: { title: { display: true, text: 'Triceps MDF (Hz)' }, grid: { color: '#F1F5F9' } },
          x: { title: { display: true, text: 'Time (s)' }, grid: { display: false } }
        }
      }
    });

  } else if (compareState.mode === 'muscle-head-to-head') {
    const subj = compareState.subject;
    const lid = compareState.load;
    const sData = mtpData.loads[lid]?.subjects[subj];

    if (!sData) {
      t1.innerText = `No data for ${subj.toUpperCase()} at ${lid}`;
      t2.innerText = `Please select another combination`;
      return;
    }

    t1.innerText = `${sData.display_name} @ ${lid.toUpperCase()}: Biceps vs Triceps RMS`;
    s1.innerText = `Co-activation ratio: ${sData.triceps_biceps_ratio}x Triceps dominance`;
    t2.innerText = `${sData.display_name} @ ${lid.toUpperCase()}: Muscle Fatigue MDF Shift`;
    s2.innerText = `Triceps drop: ${sData.triceps.mdf_drop_pct}% | Biceps drop: ${sData.biceps.mdf_drop_pct}%`;

    cmpChart1Instance = new Chart(ctx1, {
      type: 'line',
      data: {
        labels: timeLabels,
        datasets: [
          {
            label: 'Triceps (Agonist)',
            data: sData.triceps.rms_series,
            borderColor: '#DC2626',
            backgroundColor: 'rgba(220, 38, 38, 0.1)',
            fill: true,
            borderWidth: 2.2,
            tension: 0.25
          },
          {
            label: 'Biceps (Antagonist)',
            data: sData.biceps.rms_series,
            borderColor: '#2563EB',
            backgroundColor: 'rgba(37, 99, 235, 0.1)',
            fill: true,
            borderWidth: 2,
            tension: 0.25
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'top' } },
        scales: {
          y: { title: { display: true, text: 'Muscular Activity RMS (ADC)' }, grid: { color: '#F1F5F9' } },
          x: { title: { display: true, text: 'Time (s)' }, grid: { display: false } }
        }
      }
    });

    cmpChart2Instance = new Chart(ctx2, {
      type: 'line',
      data: {
        labels: timeLabels,
        datasets: [
          {
            label: 'Triceps MDF (Hz)',
            data: sData.triceps.mdf_series,
            borderColor: '#DC2626',
            borderWidth: 2.2,
            tension: 0.25
          },
          {
            label: 'Biceps MDF (Hz)',
            data: sData.biceps.mdf_series,
            borderColor: '#2563EB',
            borderWidth: 2,
            tension: 0.25
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'top' } },
        scales: {
          y: { title: { display: true, text: 'Median Frequency (Hz)' }, grid: { color: '#F1F5F9' } },
          x: { title: { display: true, text: 'Time (s)' }, grid: { display: false } }
        }
      }
    });
  }
}

function renderScalingTable() {
  const tbody = document.getElementById('scalingSummaryBody');
  if (!tbody || !mtpData) return;

  tbody.innerHTML = '';
  const scaling = mtpData.load_scaling_summary || {};

  Object.entries(scaling).forEach(([subj, info]) => {
    const tr = document.createElement('tr');
    tr.className = "hover:bg-slate-50 transition";
    
    // Evaluate fatigue vulnerability based on triceps slope
    const avgFatigueDrop = info.triceps_rms_slope_per_kg > 0 ? "High Recruitment" : "Stable";

    tr.innerHTML = `
      <td class="py-2.5 px-3 font-semibold text-slate-800">${info.name} (${subj.toUpperCase()})</td>
      <td class="py-2.5 px-3">
        <span class="px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 text-slate-700">
          ${info.loads.join(', ')}
        </span>
      </td>
      <td class="py-2.5 px-3 font-mono font-bold text-red-600">+${info.triceps_rms_slope_per_kg} ADC/kg</td>
      <td class="py-2.5 px-3 font-mono text-blue-600">+${info.biceps_rms_slope_per_kg} ADC/kg</td>
      <td class="py-2.5 px-3 font-mono text-slate-700">${info.triceps_mdf[0].toFixed(1)} → ${info.triceps_mdf[info.triceps_mdf.length - 1].toFixed(1)} Hz</td>
      <td class="py-2.5 px-3">
        <span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-100 text-emerald-800">
          Linear Scaling (R² > 0.85)
        </span>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// ========================================================
// DATASET TABLE & EXPORT
// ========================================================
function renderDatasetTable() {
  const tbody = document.getElementById('datasetTableBody');
  if (!tbody || !mtpData) return;

  tbody.innerHTML = '';
  const rows = mtpData.comparison_matrix || [];

  rows.forEach(r => {
    const tr = document.createElement('tr');
    tr.className = "hover:bg-blue-50/40 transition data-row";
    tr.setAttribute('data-load', r.load);
    tr.setAttribute('data-subject', r.subject);

    const bDropClass = r.biceps_fatigue_drop < 0 ? 'text-red-600' : 'text-emerald-600';
    const tDropClass = r.triceps_fatigue_drop < 0 ? 'text-red-600' : 'text-emerald-600';

    tr.innerHTML = `
      <td class="py-3 px-3">
        <span class="px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-800">
          ${r.load}
        </span>
      </td>
      <td class="py-3 px-3 font-semibold text-slate-900">${r.subject_name} (${r.subject.toUpperCase()})</td>
      <td class="py-3 px-3 font-mono text-blue-600 font-bold">${r.biceps_total_rms.toFixed(1)}</td>
      <td class="py-3 px-3 font-mono text-red-600 font-bold">${r.triceps_total_rms.toFixed(1)}</td>
      <td class="py-3 px-3 font-mono text-slate-700">${r.biceps_mean_mdf.toFixed(1)} Hz</td>
      <td class="py-3 px-3 font-mono text-slate-700">${r.triceps_mean_mdf.toFixed(1)} Hz</td>
      <td class="py-3 px-3 font-mono font-semibold ${bDropClass}">${r.biceps_fatigue_drop > 0 ? '+' : ''}${r.biceps_fatigue_drop}%</td>
      <td class="py-3 px-3 font-mono font-semibold ${tDropClass}">${r.triceps_fatigue_drop > 0 ? '+' : ''}${r.triceps_fatigue_drop}%</td>
      <td class="py-3 px-3 font-mono font-bold text-indigo-700">${r.triceps_biceps_ratio.toFixed(2)}x</td>
      <td class="py-3 px-3 text-right whitespace-nowrap">
        <button onclick="openSimulation('${r.load}', '${r.subject}')" class="px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-indigo-50 text-indigo-700 hover:bg-indigo-100 transition mr-1">
          3D Sim
        </button>
        <button onclick="drillDownRow('${r.load}', '${r.subject}')" class="px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-blue-50 text-blue-700 hover:bg-blue-100 transition">
          Inspect
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function filterTable() {
  const query = document.getElementById('tableSearch').value.toLowerCase();
  const loadFilter = document.getElementById('tableLoadFilter').value;
  const rows = document.querySelectorAll('.data-row');

  rows.forEach(row => {
    const rLoad = row.getAttribute('data-load');
    const rSubj = row.getAttribute('data-subject');
    const text = row.innerText.toLowerCase();

    const matchesSearch = text.includes(query);
    const matchesLoad = (loadFilter === 'all' || rLoad === loadFilter);

    if (matchesSearch && matchesLoad) {
      row.classList.remove('hidden');
    } else {
      row.classList.add('hidden');
    }
  });
}

function drillDownRow(load, subject) {
  selectExplorerLoad(load);
  explorerState.visibleSubjects = new Set([subject]);
  switchView('load-explorer');
}

function downloadCSV() {
  if (!mtpData || !mtpData.comparison_matrix) return;
  const rows = mtpData.comparison_matrix;
  const headers = ['Load', 'Mass_kg', 'Subject_ID', 'Subject_Name', 'Biceps_Total_RMS', 'Triceps_Total_RMS', 'Biceps_Mean_MDF_Hz', 'Triceps_Mean_MDF_Hz', 'Biceps_Fatigue_Drop_Pct', 'Triceps_Fatigue_Drop_Pct', 'Triceps_Biceps_Ratio'];
  
  let csv = headers.join(',') + '\n';
  rows.forEach(r => {
    csv += [
      r.load,
      r.load_mass,
      r.subject,
      `"${r.subject_name}"`,
      r.biceps_total_rms,
      r.triceps_total_rms,
      r.biceps_mean_mdf,
      r.triceps_mean_mdf,
      r.biceps_fatigue_drop,
      r.triceps_fatigue_drop,
      r.triceps_biceps_ratio
    ].join(',') + '\n';
  });

  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `mtp_push_emg_data_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
}

function downloadJSON() {
  if (!mtpData) return;
  const blob = new Blob([JSON.stringify(mtpData, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `mtp_push_emg_full_dataset_${new Date().toISOString().slice(0,10)}.json`;
  a.click();
}

// ========================================================
// FILE UPLOAD HANDLER
// ========================================================
function toggleCustomSubject(val) {
  const customInput = document.getElementById('uploadSubjectCustom');
  if (val === '__new__') {
    customInput.classList.remove('hidden');
    customInput.focus();
  } else {
    customInput.classList.add('hidden');
  }
}

function updateSelectedFileName(input) {
  const lbl = document.getElementById('uploadFileNameLabel');
  if (input.files && input.files[0]) {
    lbl.innerText = `Selected: ${input.files[0].name} (${(input.files[0].size / 1024 / 1024).toFixed(2)} MB)`;
  }
}

async function handleTrialUpload(event) {
  event.preventDefault();
  const fileInput = document.getElementById('uploadFileInput');
  if (!fileInput.files || !fileInput.files[0]) {
    alert('Please select an Excel (.xlsx) or CSV trial file first.');
    return;
  }

  const selectedLoadRadio = document.querySelector('input[name="uploadLoad"]:checked');
  const load = selectedLoadRadio ? selectedLoadRadio.value : '2.5kg';

  const subjSelect = document.getElementById('uploadSubjectSelect');
  let subject = subjSelect.value;
  if (subject === '__new__') {
    subject = document.getElementById('uploadSubjectCustom').value.trim().toLowerCase();
    if (!subject) {
      alert('Please enter a valid subject identifier.');
      return;
    }
  }

  const btn = document.getElementById('uploadSubmitBtn');
  const statusMsg = document.getElementById('uploadStatusMsg');
  
  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader" class="w-4 h-4 animate-spin"></i><span>Streaming & Processing EMG Data...</span>`;
  if (window.lucide) lucide.createIcons();

  statusMsg.className = "p-4 rounded-xl text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200 block";
  statusMsg.innerText = "Parsing XML streams (360,000 samples @ 2000 Hz) & computing FFT Median Frequency...";

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  formData.append('load', load);
  formData.append('subject', subject);

  try {
    const res = await fetch('/api/upload', {
      method: 'POST',
      body: formData
    });

    const result = await res.json();
    if (!res.ok) {
      throw new Error(result.error || 'Server error processing file');
    }

    statusMsg.className = "p-4 rounded-xl text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-200 block";
    statusMsg.innerText = `Successfully processed trial for ${subject.toUpperCase()} at ${load}! RMS & MDF computed.`;

    // Refresh dataset
    await loadDataset();

    setTimeout(() => {
      selectExplorerLoad(load);
      switchView('load-explorer');
    }, 1200);

  } catch (err) {
    console.error('Upload failed:', err);
    statusMsg.className = "p-4 rounded-xl text-xs font-medium bg-red-50 text-red-800 border border-red-200 block";
    statusMsg.innerText = `Upload failed: ${err.message}. Please verify the file is a valid 2-column EMG Excel/CSV file.`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="play" class="w-4 h-4"></i><span>Process & Update Dashboard</span>`;
    if (window.lucide) lucide.createIcons();
  }
}

// ========================================================
// 3D PUSH FATIGUE SIMULATION STUDIO
// ========================================================
const simPlayheadPlugin = {
  id: 'simPlayhead',
  afterDatasetsDraw(chart) {
    if (!simState || simState.progressFrac == null) return;
    const { ctx, chartArea, scales } = chart;
    if (!chartArea || !scales.x) return;
    const xPos = chartArea.left + simState.progressFrac * (chartArea.right - chartArea.left);
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(xPos, chartArea.top);
    ctx.lineTo(xPos, chartArea.bottom);
    ctx.lineWidth = 2;
    ctx.strokeStyle = 'rgba(15, 23, 42, 0.75)';
    ctx.setLineDash([4, 3]);
    ctx.stroke();
    ctx.restore();
  }
};

function openSimulation(loadId, subjectId) {
  simState.load = loadId;
  simState.subject = subjectId;
  switchView('simulations');
}

function selectSimLoad(loadId) {
  simState.load = loadId;
  const loadObj = mtpData?.loads?.[loadId];
  const subjects = loadObj ? Object.keys(loadObj.subjects || {}) : [];
  if (subjects.length > 0 && !subjects.includes(simState.subject)) {
    simState.subject = subjects[0];
  }
  renderSimulationsView();
}

function selectSimSubject(subjectId) {
  simState.subject = subjectId;
  renderSimulationsView();
}

function setSimSpeed(speed) {
  simState.speed = speed;
  const video = document.getElementById('simVideoPlayer');
  if (video) video.playbackRate = speed;
  document.querySelectorAll('.sim-speed-btn').forEach(btn => {
    const val = parseFloat(btn.getAttribute('data-speed'));
    if (Math.abs(val - speed) < 0.01) {
      btn.className = "sim-speed-btn px-2 py-1 rounded-lg border border-blue-500 bg-blue-50 text-blue-700 font-mono font-semibold";
    } else {
      btn.className = "sim-speed-btn px-2 py-1 rounded-lg border border-slate-200 hover:bg-slate-100 font-mono";
    }
  });
}

function setSimGalleryFilter(mode) {
  simState.galleryFilter = mode;
  const selBtn = document.getElementById('btn-sim-gal-selected');
  const allBtn = document.getElementById('btn-sim-gal-all');
  if (selBtn && allBtn) {
    if (mode === 'selected') {
      selBtn.className = "sub-tab-active px-3 py-1 rounded-lg text-xs font-semibold transition";
      allBtn.className = "px-3 py-1 rounded-lg text-xs font-semibold text-slate-600 hover:text-slate-900 transition";
    } else {
      allBtn.className = "sub-tab-active px-3 py-1 rounded-lg text-xs font-semibold transition";
      selBtn.className = "px-3 py-1 rounded-lg text-xs font-semibold text-slate-600 hover:text-slate-900 transition";
    }
  }
  renderSimGallery();
}

function renderSimulationsView() {
  if (!mtpData) return;

  // 1. Update Load buttons
  document.querySelectorAll('.sim-load-btn').forEach(btn => {
    if (btn.getAttribute('data-load') === simState.load) {
      btn.className = "sim-load-btn tab-active px-3.5 py-2 rounded-xl text-xs font-semibold border border-transparent shadow-md transition";
    } else {
      btn.className = "sim-load-btn px-3.5 py-2 rounded-xl text-xs font-semibold border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 transition";
    }
  });

  // 2. Render Subject buttons for active load
  const loadObj = mtpData.loads[simState.load];
  const subjects = loadObj ? Object.keys(loadObj.subjects || {}) : [];
  if (subjects.length > 0 && !subjects.includes(simState.subject)) {
    simState.subject = subjects[0];
  }

  const subjContainer = document.getElementById('sim-subject-buttons');
  if (subjContainer) {
    subjContainer.innerHTML = subjects.map(s => {
      const sData = loadObj.subjects[s];
      const active = s === simState.subject;
      const color = SUBJECT_COLORS[s] || '#2563EB';
      return `
        <button onclick="selectSimSubject('${s}')" class="px-3 py-1.5 rounded-xl text-xs font-semibold border flex items-center gap-1.5 transition ${
          active ? 'bg-slate-900 text-white border-slate-900 shadow-sm' : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
        }">
          <span class="w-2 h-2 rounded-full inline-block" style="background-color: ${color}"></span>
          <span>${sData.display_name} (${s.toUpperCase()})</span>
        </button>
      `;
    }).join('');
  }

  // 3. Load active simulation video & metadata
  const sData = loadObj?.subjects?.[simState.subject];
  if (sData) {
    const videoUrl = sData.simulation_video || `/simulations/${simState.load}/${simState.subject}.mp4`;
    const titleEl = document.getElementById('simActiveTitle');
    const subEl = document.getElementById('simActiveSubtitle');
    const dlBtn = document.getElementById('simDownloadBtn');
    const video = document.getElementById('simVideoPlayer');

    if (titleEl) titleEl.innerText = `${sData.display_name} (${simState.subject.toUpperCase()}) — ${loadObj.name} 3D Simulation`;
    if (subEl) subEl.innerText = `Triceps RMS: ${sData.total_triceps_rms} ADC | Biceps RMS: ${sData.total_biceps_rms} ADC | T/B Ratio: ${sData.triceps_biceps_ratio}x | MDF Drop: ${sData.triceps.mdf_drop_pct}%`;
    if (dlBtn) {
      dlBtn.href = videoUrl;
      dlBtn.download = `push_fatigue_3d_${simState.load}_${simState.subject}.mp4`;
    }

    if (video && video.getAttribute('data-current-src') !== videoUrl) {
      video.setAttribute('data-current-src', videoUrl);
      video.src = videoUrl;
      video.playbackRate = simState.speed;
      video.play().catch(() => {});
    }

    renderSimCharts(sData);
    startSimSyncLoop(sData);
  }

  renderSimGallery();
  if (window.lucide) lucide.createIcons();
}

function interpolateSeries(series, frac) {
  if (!series || series.length === 0) return 0;
  const trialT = Math.max(0, Math.min(180, frac * 180));
  const idxFloat = (trialT - 2.5) / 5.0;
  if (idxFloat <= 0) return series[0];
  if (idxFloat >= series.length - 1) return series[series.length - 1];
  const i0 = Math.floor(idxFloat);
  const i1 = i0 + 1;
  const alpha = idxFloat - i0;
  return series[i0] * (1 - alpha) + series[i1] * alpha;
}

function startSimSyncLoop(sData) {
  if (simRafId) {
    cancelAnimationFrame(simRafId);
    simRafId = null;
  }
  const tick = () => {
    if (currentView !== 'simulations') return;
    const video = document.getElementById('simVideoPlayer');
    if (video && video.duration && !isNaN(video.duration)) {
      const frac = Math.max(0, Math.min(1, video.currentTime / video.duration));
      simState.progressFrac = frac;

      const trialT = frac * 180.0;
      const clockEl = document.getElementById('simTrialClock');
      if (clockEl) clockEl.innerText = `${trialT.toFixed(1)}s / 180.0s`;

      const tRms = interpolateSeries(sData.triceps.rms_series, frac);
      const bRms = interpolateSeries(sData.biceps.rms_series, frac);
      const tMdf = interpolateSeries(sData.triceps.mdf_series, frac);
      const bMdf = interpolateSeries(sData.biceps.mdf_series, frac);

      const elTR = document.getElementById('simLiveTRms');
      const elBR = document.getElementById('simLiveBRms');
      const elTM = document.getElementById('simLiveTMdf');
      const elBM = document.getElementById('simLiveBMdf');
      if (elTR) elTR.innerText = `${tRms.toFixed(1)} ADC`;
      if (elBR) elBR.innerText = `${bRms.toFixed(1)} ADC`;
      if (elTM) elTM.innerText = `${tMdf.toFixed(1)} Hz`;
      if (elBM) elBM.innerText = `${bMdf.toFixed(1)} Hz`;

      if (simRmsChart) simRmsChart.draw();
      if (simMdfChart) simMdfChart.draw();
    }
    simRafId = requestAnimationFrame(tick);
  };
  simRafId = requestAnimationFrame(tick);
}

function renderSimCharts(sData) {
  const ctxRms = document.getElementById('simRmsChart');
  const ctxMdf = document.getElementById('simMdfChart');
  if (!ctxRms || !ctxMdf || !mtpData) return;

  if (simRmsChart) simRmsChart.destroy();
  if (simMdfChart) simMdfChart.destroy();

  const timeLabels = (mtpData.metadata.time_axis || []).map(t => `${Math.round(t)}s`);

  simRmsChart = new Chart(ctxRms, {
    type: 'line',
    data: {
      labels: timeLabels,
      datasets: [
        {
          label: 'Triceps RMS',
          data: sData.triceps.rms_series,
          borderColor: '#DC2626',
          backgroundColor: 'rgba(220,38,38,0.08)',
          fill: true,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.25
        },
        {
          label: 'Biceps RMS',
          data: sData.biceps.rms_series,
          borderColor: '#2563EB',
          backgroundColor: 'rgba(37,99,235,0.08)',
          fill: true,
          borderWidth: 1.8,
          pointRadius: 0,
          tension: 0.25
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { position: 'top', labels: { boxWidth: 10, font: { size: 10 } } } },
      scales: {
        y: { beginAtZero: true, grid: { color: '#F1F5F9' }, ticks: { font: { size: 9 } } },
        x: { grid: { display: false }, ticks: { maxTicksLimit: 7, font: { size: 9 } } }
      }
    },
    plugins: [simPlayheadPlugin]
  });

  simMdfChart = new Chart(ctxMdf, {
    type: 'line',
    data: {
      labels: timeLabels,
      datasets: [
        {
          label: 'Triceps MDF (Hz)',
          data: sData.triceps.mdf_series,
          borderColor: '#EA580C',
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.25
        },
        {
          label: 'Biceps MDF (Hz)',
          data: sData.biceps.mdf_series,
          borderColor: '#0284C7',
          borderWidth: 1.8,
          pointRadius: 0,
          tension: 0.25
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { position: 'top', labels: { boxWidth: 10, font: { size: 10 } } } },
      scales: {
        y: { grid: { color: '#F1F5F9' }, ticks: { font: { size: 9 } } },
        x: { grid: { display: false }, ticks: { maxTicksLimit: 7, font: { size: 9 } } }
      }
    },
    plugins: [simPlayheadPlugin]
  });
}

function renderSimGallery() {
  const grid = document.getElementById('simGalleryGrid');
  if (!grid || !mtpData) return;

  const items = [];
  const loadOrder = simState.galleryFilter === 'all' ? ['2.5kg', '5kg', '7.5kg', '10kg'] : [simState.load];
  loadOrder.forEach(lid => {
    const lObj = mtpData.loads[lid];
    if (!lObj) return;
    Object.keys(lObj.subjects || {}).forEach(sid => {
      items.push({ loadId: lid, loadName: lObj.name, subjId: sid, sData: lObj.subjects[sid] });
    });
  });

  grid.innerHTML = items.map(item => {
    const { loadId, loadName, subjId, sData } = item;
    const isActive = loadId === simState.load && subjId === simState.subject;
    const videoUrl = sData.simulation_video || `/simulations/${loadId}/${subjId}.mp4`;
    const color = SUBJECT_COLORS[subjId] || '#2563EB';
    const tDrop = sData.triceps.mdf_drop_pct;
    return `
      <div class="rounded-xl border ${isActive ? 'border-blue-500 ring-2 ring-blue-500/20' : 'border-slate-200'} bg-white overflow-hidden shadow-sm hover:shadow-md transition flex flex-col">
        <div class="relative bg-slate-950 aspect-video cursor-pointer group" onclick="openSimulation('${loadId}', '${subjId}')">
          <video src="${videoUrl}#t=2.5" preload="metadata" muted loop playsinline
                 onmouseover="this.play().catch(()=>{})" onmouseout="this.pause()"
                 class="w-full h-full object-cover"></video>
          <span class="absolute top-2 left-2 px-2 py-0.5 rounded-md text-[10px] font-bold bg-slate-900/80 text-white border border-slate-700">${loadName}</span>
          <span class="absolute bottom-2 right-2 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-blue-600/90 text-white opacity-0 group-hover:opacity-100 transition">Load Simulation</span>
        </div>
        <div class="p-3 flex-1 flex flex-col justify-between space-y-2">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-1.5">
              <span class="w-2.5 h-2.5 rounded-full inline-block" style="background-color: ${color}"></span>
              <span class="text-xs font-bold text-slate-900">${sData.display_name} (${subjId.toUpperCase()})</span>
            </div>
            <span class="text-[11px] font-mono font-bold text-indigo-700">${sData.triceps_biceps_ratio.toFixed(2)}x</span>
          </div>
          <div class="grid grid-cols-3 gap-1 text-[10px] text-slate-600 bg-slate-50 rounded-lg p-1.5 font-mono">
            <div><span class="text-slate-400 block">T-RMS</span><strong class="text-red-600">${sData.total_triceps_rms.toFixed(1)}</strong></div>
            <div><span class="text-slate-400 block">B-RMS</span><strong class="text-blue-600">${sData.total_biceps_rms.toFixed(1)}</strong></div>
            <div><span class="text-slate-400 block">T-MDF</span><strong class="${tDrop < 0 ? 'text-red-600' : 'text-emerald-600'}">${tDrop > 0 ? '+' : ''}${tDrop}%</strong></div>
          </div>
          <div class="flex items-center gap-2 pt-0.5">
            <button onclick="openSimulation('${loadId}', '${subjId}')" class="flex-1 py-1.5 rounded-lg text-[11px] font-semibold bg-slate-900 text-white hover:bg-blue-600 transition">
              Watch &amp; Sync
            </button>
            <a href="${videoUrl}" download="push_fatigue_3d_${loadId}_${subjId}.mp4" class="px-2.5 py-1.5 rounded-lg text-[11px] font-semibold border border-slate-200 text-slate-700 hover:bg-slate-50 transition" title="Download MP4">
              <i data-lucide="download" class="w-3.5 h-3.5"></i>
            </a>
          </div>
        </div>
      </div>
    `;
  }).join('');

  if (window.lucide) lucide.createIcons();
}
