const state = {
  meta: null,
  reports: [],
  selectedReport: null,
  selectedWorkflow: "factor-pipeline",
  formValues: {},
  tasks: [],
  activeTaskId: null,
};

const DEFAULTS = {
  train_start: "2016-01-01",
  train_end: "2021-12-31",
  oos_start: "2022-01-01",
  oos_end: "2024-12-31",
  walk_forward_start: "2016-01-01",
  walk_forward_end: "2024-12-31",
  start: "2016-01-01",
  end: "2024-12-31",
  optimize_start: "2016-01-01",
  optimize_end: "2021-12-31",
  test_start: "2022-01-01",
  test_end: "2024-12-31",
  train_years: 3,
  test_months: 6,
  step_months: 6,
  gap_days: 1,
  top_n: 10,
  rebalance_every_n_days: 1,
  target_max_dd: 0.15,
  gross_exposure_grid: "0.3,0.35,0.4",
  top_n_grid: "8,10,12",
  stop_loss_grid: "0.02,0.025,0.03",
  trailing_stop_grid: "1.0,1.25,1.5",
  max_holding_days_grid: "2,3,4",
  objective: "calmar",
  max_strategies: 3,
  overwrite_frozen: true,
  dry_run: true,
};

const WORKFLOWS = {
  "factor-pipeline": {
    label: "Factor Pipeline",
    description: "一站式跑因子研究、筛选、OOS 组合回测和 walk-forward，适合第一次让朋友体验完整流程。",
    command: "factor-pipeline",
    fields: [
      { key: "train_start", label: "训练开始", type: "date" },
      { key: "train_end", label: "训练结束", type: "date" },
      { key: "oos_start", label: "OOS 开始", type: "date" },
      { key: "oos_end", label: "OOS 结束", type: "date" },
      { key: "walk_forward_start", label: "WF 开始", type: "date" },
      { key: "walk_forward_end", label: "WF 结束", type: "date" },
      { key: "candidate_factors", label: "候选因子", type: "multi-factor", full: true, help: "留空表示用默认全集。" },
      { key: "top_n", label: "Top N", type: "number" },
      { key: "rebalance_every_n_days", label: "调仓间隔", type: "number" },
      { key: "train_years", label: "训练年数", type: "number" },
      { key: "test_months", label: "测试月数", type: "number" },
      { key: "step_months", label: "步长月数", type: "number" },
      { key: "gap_days", label: "Gap Days", type: "number" },
      { key: "overwrite_frozen", label: "覆盖冻结结果", type: "checkbox" },
    ],
  },
  "factor-research": {
    label: "Factor Research",
    description: "只跑单因子研究，适合先让朋友看因子强弱和方向。",
    command: "factor-research",
    fields: [
      { key: "train_start", label: "训练开始", type: "date" },
      { key: "train_end", label: "训练结束", type: "date" },
      { key: "oos_start", label: "OOS 开始", type: "date" },
      { key: "oos_end", label: "OOS 结束", type: "date" },
      { key: "candidate_factors", label: "候选因子", type: "multi-factor", full: true },
    ],
  },
  "factor-select": {
    label: "Factor Select",
    description: "从 train/OOS 表现中挑稳定因子并冻结模型。",
    command: "factor-select",
    fields: [
      { key: "train_start", label: "训练开始", type: "date" },
      { key: "train_end", label: "训练结束", type: "date" },
      { key: "oos_start", label: "OOS 开始", type: "date" },
      { key: "oos_end", label: "OOS 结束", type: "date" },
      { key: "candidate_factors", label: "候选因子", type: "multi-factor", full: true },
      { key: "overwrite_frozen", label: "覆盖冻结结果", type: "checkbox" },
    ],
  },
  "composite-backtest": {
    label: "Composite Backtest",
    description: "把筛选后的稳定因子合成组合分数并做 OOS 回测。",
    command: "composite-backtest",
    fields: [
      { key: "train_start", label: "训练开始", type: "date" },
      { key: "train_end", label: "训练结束", type: "date" },
      { key: "oos_start", label: "OOS 开始", type: "date" },
      { key: "oos_end", label: "OOS 结束", type: "date" },
      { key: "candidate_factors", label: "候选因子", type: "multi-factor", full: true },
      { key: "top_n", label: "Top N", type: "number" },
      { key: "rebalance_every_n_days", label: "调仓间隔", type: "number" },
    ],
  },
  "factor-walk-forward": {
    label: "Factor Walk Forward",
    description: "检查不同滚动窗口下的因子组合稳定性。",
    command: "factor-walk-forward",
    fields: [
      { key: "start", label: "开始日期", type: "date" },
      { key: "end", label: "结束日期", type: "date" },
      { key: "candidate_factors", label: "候选因子", type: "multi-factor", full: true },
      { key: "train_years", label: "训练年数", type: "number" },
      { key: "test_months", label: "测试月数", type: "number" },
      { key: "step_months", label: "步长月数", type: "number" },
      { key: "gap_days", label: "Gap Days", type: "number" },
      { key: "top_n", label: "Top N", type: "number" },
    ],
  },
  "alpha-combo-search": {
    label: "Alpha Combo Search",
    description: "搜索低相关多因子组合，适合朋友从多个 alpha 候选里挑组合。",
    command: "alpha-combo-search",
    fields: [
      { key: "train_start", label: "训练开始", type: "date" },
      { key: "train_end", label: "训练结束", type: "date" },
      { key: "oos_start", label: "OOS 开始", type: "date" },
      { key: "oos_end", label: "OOS 结束", type: "date" },
      { key: "candidate_factors", label: "候选因子", type: "multi-factor", full: true },
      { key: "top_n", label: "Top N", type: "number" },
      { key: "rebalance_every_n_days", label: "调仓间隔", type: "number" },
    ],
  },
  "alpha-combo-walk-forward": {
    label: "Combo Walk Forward",
    description: "对低相关 alpha 组合做滚动窗口验证。",
    command: "alpha-combo-walk-forward",
    fields: [
      { key: "start", label: "开始日期", type: "date" },
      { key: "end", label: "结束日期", type: "date" },
      { key: "candidate_factors", label: "候选因子", type: "multi-factor", full: true },
      { key: "train_years", label: "训练年数", type: "number" },
      { key: "test_months", label: "测试月数", type: "number" },
      { key: "step_months", label: "步长月数", type: "number" },
      { key: "gap_days", label: "Gap Days", type: "number" },
      { key: "top_n", label: "Top N", type: "number" },
      { key: "rebalance_every_n_days", label: "调仓间隔", type: "number" },
    ],
  },
  "alpha-combo-risk-search": {
    label: "Risk Search",
    description: "在已冻结的低相关组合上搜索更保守的风控参数。",
    command: "alpha-combo-risk-search",
    fields: [
      { key: "train_start", label: "训练开始", type: "date" },
      { key: "train_end", label: "训练结束", type: "date" },
      { key: "oos_start", label: "OOS 开始", type: "date" },
      { key: "oos_end", label: "OOS 结束", type: "date" },
      { key: "target_max_dd", label: "目标最大回撤", type: "number", step: "0.01" },
      { key: "gross_exposure_grid", label: "总敞口网格", type: "text", full: true, help: "逗号分隔，例如 0.3,0.35,0.4" },
      { key: "top_n_grid", label: "Top N 网格", type: "text", full: true },
      { key: "stop_loss_grid", label: "止损网格", type: "text", full: true },
      { key: "trailing_stop_grid", label: "ATR 追踪止损网格", type: "text", full: true },
      { key: "max_holding_days_grid", label: "最大持有天数网格", type: "text", full: true },
    ],
  },
  train: {
    label: "Train",
    description: "跑老策略训练和参数冻结，适合做对照组研究。",
    command: "train",
    fields: [
      { key: "start", label: "开始日期", type: "date" },
      { key: "end", label: "结束日期", type: "date" },
      { key: "strategies", label: "策略", type: "multi-strategy", full: true },
      { key: "objective", label: "目标函数", type: "select", options: ["sharpe", "cagr", "calmar"] },
      { key: "overwrite_frozen", label: "覆盖冻结结果", type: "checkbox" },
    ],
  },
  test: {
    label: "Test",
    description: "跑样本外测试，检验冻结参数的 OOS 结果。",
    command: "test",
    fields: [
      { key: "start", label: "开始日期", type: "date" },
      { key: "end", label: "结束日期", type: "date" },
      { key: "strategies", label: "策略", type: "multi-strategy", full: true },
    ],
  },
  "walk-forward": {
    label: "Strategy Walk Forward",
    description: "老策略滚动验证入口。",
    command: "walk-forward",
    fields: [
      { key: "start", label: "开始日期", type: "date" },
      { key: "end", label: "结束日期", type: "date" },
      { key: "strategies", label: "策略", type: "multi-strategy", full: true },
      { key: "train_years", label: "训练年数", type: "number" },
      { key: "test_months", label: "测试月数", type: "number" },
      { key: "step_months", label: "步长月数", type: "number" },
      { key: "gap_days", label: "Gap Days", type: "number" },
    ],
  },
  pipeline: {
    label: "Legacy Pipeline",
    description: "旧策略主线的一键流程，保留给熟悉项目的人使用。",
    command: "pipeline",
    fields: [
      { key: "optimize_start", label: "优化开始", type: "date" },
      { key: "optimize_end", label: "优化结束", type: "date" },
      { key: "test_start", label: "测试开始", type: "date" },
      { key: "test_end", label: "测试结束", type: "date" },
      { key: "walk_forward_start", label: "WF 开始", type: "date" },
      { key: "walk_forward_end", label: "WF 结束", type: "date" },
      { key: "candidate_strategies", label: "候选策略", type: "multi-strategy", full: true },
      { key: "objective", label: "目标函数", type: "select", options: ["sharpe", "cagr", "calmar"] },
      { key: "max_strategies", label: "最多策略数", type: "number" },
      { key: "train_years", label: "训练年数", type: "number" },
      { key: "test_months", label: "测试月数", type: "number" },
      { key: "step_months", label: "步长月数", type: "number" },
      { key: "gap_days", label: "Gap Days", type: "number" },
      { key: "overwrite_frozen", label: "覆盖冻结结果", type: "checkbox" },
    ],
  },
  deploy: {
    label: "Deploy Dry Run",
    description: "只保留 dry-run 给朋友查看组合结果，不建议直接开放真实下单。",
    command: "deploy",
    fields: [{ key: "dry_run", label: "只做 Dry Run", type: "checkbox" }],
  },
};

function $(selector) {
  return document.querySelector(selector);
}

function formatNumber(value, digits = 3) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "N/A";
  return Number(value).toFixed(digits);
}

function formatPercent(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "N/A";
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

function formatDateText(value) {
  if (!value) return "N/A";
  return String(value).replace("T", " ").replace("Z", " UTC");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function parseListInput(value, numeric = false) {
  if (Array.isArray(value)) return value;
  if (!value) return [];
  return String(value)
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => (numeric ? Number(item) : item));
}

function getDefaultValue(key) {
  if (Object.prototype.hasOwnProperty.call(DEFAULTS, key)) return DEFAULTS[key];
  if (key === "strategies" || key === "candidate_strategies") return state.meta?.strategies?.slice(0, 2) || [];
  if (key === "candidate_factors") return [];
  return "";
}

function resetWorkflowValues(workflowKey) {
  const workflow = WORKFLOWS[workflowKey];
  const nextValues = {};
  workflow.fields.forEach((field) => {
    nextValues[field.key] = getDefaultValue(field.key);
  });
  state.formValues = nextValues;
}

function getSelectedWorkflow() {
  return WORKFLOWS[state.selectedWorkflow];
}

function switchSection(section) {
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.section === section));
  document.querySelectorAll(".content-section").forEach((panel) => panel.classList.toggle("active", panel.id === `section-${section}`));
}

function renderNav() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => switchSection(button.dataset.section));
  });
}

function renderOverview() {
  const meta = state.meta;
  if (!meta) {
    $("#meta-list").innerHTML = `<p class="empty-state">正在读取环境信息...</p>`;
    return;
  }

  const rows = [
    ["仓库目录", meta.repo_dir],
    ["前端目录", meta.web_dir],
    ["任务 Python", meta.python_executable],
    ["服务器时间", meta.server_time_utc],
  ];

  $("#meta-list").innerHTML = rows
    .map(
      ([label, value]) => `
        <div class="meta-row">
          <strong>${escapeHtml(label)}</strong>
          <span>${escapeHtml(value)}</span>
        </div>
      `,
    )
    .join("");

  $("#factor-wall").innerHTML = (meta.factors || []).map((factor) => `<span class="chip">${escapeHtml(factor)}</span>`).join("");
  $("#strategy-wall").innerHTML = (meta.strategies || []).map((strategy) => `<span class="chip">${escapeHtml(strategy)}</span>`).join("");

  const quickActions = [
    { key: "factor-pipeline", title: "完整因子研究", copy: "最适合第一次带朋友跑完整流程。" },
    { key: "alpha-combo-search", title: "找低相关组合", copy: "让朋友从多个 alpha 组合里挑方向。" },
    { key: "alpha-combo-risk-search", title: "做保守版风险搜索", copy: "把回撤目标收紧，看更稳的参数方案。" },
  ];

  $("#quick-actions").innerHTML = quickActions
    .map(
      (item) => `
        <button class="quick-card" data-workflow-jump="${item.key}">
          <p class="panel-kicker">${escapeHtml(item.title)}</p>
          <div>${escapeHtml(item.copy)}</div>
        </button>
      `,
    )
    .join("");

  document.querySelectorAll("[data-workflow-jump]").forEach((button) => {
    button.addEventListener("click", () => {
      switchSection("lab");
      selectWorkflow(button.dataset.workflowJump);
    });
  });

  const recent = (state.reports || []).slice(0, 6);
  $("#recent-reports").innerHTML = recent
    .map(
      (report) => `
        <button class="report-card" data-report-jump="${report.name}">
          <p class="panel-kicker">${escapeHtml(report.name.replace(".json", ""))}</p>
          <div>${formatDateText(report.mtime)}</div>
        </button>
      `,
    )
    .join("");

  document.querySelectorAll("[data-report-jump]").forEach((button) => {
    button.addEventListener("click", async () => {
      switchSection("reports");
      await selectReport(button.dataset.reportJump);
    });
  });
}

function renderWorkflowList() {
  $("#workflow-list").innerHTML = Object.entries(WORKFLOWS)
    .map(
      ([key, workflow]) => `
        <button class="workflow-card ${state.selectedWorkflow === key ? "active" : ""}" data-workflow="${key}">
          <p class="panel-kicker">${escapeHtml(workflow.label)}</p>
          <div>${escapeHtml(workflow.description)}</div>
        </button>
      `,
    )
    .join("");

  document.querySelectorAll("[data-workflow]").forEach((button) => {
    button.addEventListener("click", () => selectWorkflow(button.dataset.workflow));
  });
}

function renderCheckboxField(field, options) {
  const values = Array.isArray(state.formValues[field.key]) ? state.formValues[field.key] : [];
  return `
    <div class="field-group ${field.full ? "full" : ""}">
      <label>${escapeHtml(field.label)}</label>
      <div class="checkbox-grid">
        ${options
          .map(
            (option) => `
              <label class="checkbox-chip">
                <input type="checkbox" data-key="${field.key}" data-kind="multi" value="${escapeHtml(option)}" ${
                  values.includes(option) ? "checked" : ""
                } />
                <span>${escapeHtml(option)}</span>
              </label>
            `,
          )
          .join("")}
      </div>
      ${field.help ? `<div class="field-help">${escapeHtml(field.help)}</div>` : ""}
    </div>
  `;
}

function buildCommandPreview() {
  const workflow = getSelectedWorkflow();
  const args = ["python", "main.py", workflow.command];

  workflow.fields.forEach((field) => {
    const value = state.formValues[field.key];
    if (field.type === "checkbox") {
      if (field.key === "overwrite_frozen") {
        args.push(value ? "--overwrite-frozen" : "--no-overwrite-frozen");
      } else if (field.key === "dry_run" && value) {
        args.push("--dry-run");
      }
      return;
    }

    if (field.type === "multi-factor") {
      if (value?.length) args.push("--candidate-factors", ...value);
      return;
    }

    if (field.type === "multi-strategy") {
      if (field.key === "candidate_strategies" && value?.length) {
        args.push("--candidate-strategies", ...value);
      } else if (value?.length) {
        args.push("--strategies", ...value);
      }
      return;
    }

    if (value === "" || value === null || value === undefined) return;
    args.push(`--${field.key.replaceAll("_", "-")}`, String(value));
  });

  return args.join(" ");
}

function handleFieldChange(event) {
  const target = event.target;
  const key = target.dataset.key;
  const kind = target.dataset.kind;

  if (kind === "multi") {
    const checked = Array.from(document.querySelectorAll(`input[data-key="${key}"]:checked`)).map((input) => input.value);
    state.formValues[key] = checked;
  } else if (kind === "checkbox") {
    state.formValues[key] = target.checked;
  } else if (kind === "number") {
    state.formValues[key] = target.value === "" ? "" : Number(target.value);
  } else {
    state.formValues[key] = target.value;
  }

  $("#command-preview-text").textContent = buildCommandPreview();
}

function renderWorkflowForm() {
  const workflow = getSelectedWorkflow();
  $("#form-title").textContent = workflow.label;
  $("#workflow-description").textContent = workflow.description;
  $("#form-fields").innerHTML = workflow.fields
    .map((field) => {
      if (field.type === "multi-factor") return renderCheckboxField(field, state.meta?.factors || []);
      if (field.type === "multi-strategy") return renderCheckboxField(field, state.meta?.strategies || []);
      if (field.type === "checkbox") {
        return `
          <div class="field-group ${field.full ? "full" : ""}">
            <label class="checkbox-chip">
              <input type="checkbox" data-key="${field.key}" data-kind="checkbox" ${state.formValues[field.key] ? "checked" : ""} />
              <span>${escapeHtml(field.label)}</span>
            </label>
          </div>
        `;
      }
      if (field.type === "select") {
        return `
          <div class="field-group ${field.full ? "full" : ""}">
            <label>${escapeHtml(field.label)}</label>
            <select data-key="${field.key}" data-kind="select">
              ${field.options
                .map(
                  (option) =>
                    `<option value="${escapeHtml(option)}" ${state.formValues[field.key] === option ? "selected" : ""}>${escapeHtml(option)}</option>`,
                )
                .join("")}
            </select>
          </div>
        `;
      }
      return `
        <div class="field-group ${field.full ? "full" : ""}">
          <label>${escapeHtml(field.label)}</label>
          <input type="${field.type || "text"}" data-key="${field.key}" data-kind="${field.type || "text"}" value="${escapeHtml(
            state.formValues[field.key] ?? "",
          )}" ${field.step ? `step="${field.step}"` : ""} />
          ${field.help ? `<div class="field-help">${escapeHtml(field.help)}</div>` : ""}
        </div>
      `;
    })
    .join("");

  $("#command-preview-text").textContent = buildCommandPreview();

  $("#form-fields").querySelectorAll("[data-key]").forEach((input) => {
    input.addEventListener("input", handleFieldChange);
    input.addEventListener("change", handleFieldChange);
  });
}

function selectWorkflow(workflowKey) {
  state.selectedWorkflow = workflowKey;
  resetWorkflowValues(workflowKey);
  renderWorkflowList();
  renderWorkflowForm();
}

function renderTasks() {
  $("#task-list").innerHTML = state.tasks.length
    ? state.tasks
        .map(
          (task) => `
            <button class="task-item ${state.activeTaskId === task.id ? "active" : ""}" data-task-id="${task.id}">
              <p class="panel-kicker">${escapeHtml(task.workflow)}</p>
              <div><strong>${escapeHtml(task.status)}</strong></div>
              <div class="muted">${escapeHtml(formatDateText(task.created_at))}</div>
            </button>
          `,
        )
        .join("")
    : `<p class="empty-state">任务列表为空。</p>`;

  document.querySelectorAll("[data-task-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeTaskId = button.dataset.taskId;
      renderTasks();
      renderTaskDetail();
    });
  });

  renderTaskDetail();
}

function renderTaskDetail() {
  const task = state.tasks.find((item) => item.id === state.activeTaskId) || state.tasks[0];
  if (!task) {
    $("#task-detail").innerHTML = `<p class="empty-state">还没有任务。提交一个研究流程后，这里会显示执行日志和新生成的报告。</p>`;
    return;
  }

  state.activeTaskId = task.id;
  const reportLinks = (task.new_reports || [])
    .map((name) => `<button class="ghost-btn small" data-open-report="${escapeHtml(name)}">${escapeHtml(name)}</button>`)
    .join("");

  $("#task-detail").innerHTML = `
    <div class="section-stack">
      <div class="summary-grid">
        <div class="summary-card"><div class="panel-kicker">Status</div><span class="value">${escapeHtml(task.status)}</span></div>
        <div class="summary-card"><div class="panel-kicker">Created</div><span class="value">${escapeHtml(formatDateText(task.created_at))}</span></div>
        <div class="summary-card"><div class="panel-kicker">Finished</div><span class="value">${escapeHtml(formatDateText(task.finished_at))}</span></div>
      </div>
      <div class="note-box">
        <p class="panel-kicker">Command</p>
        <pre class="raw-json">${escapeHtml(task.command)}</pre>
      </div>
      ${reportLinks ? `<div><p class="panel-kicker">New Reports</p><div class="pill-row">${reportLinks}</div></div>` : ""}
      <div>
        <p class="panel-kicker">Log</p>
        <pre class="log-box">${escapeHtml(task.log || "暂无输出")}</pre>
      </div>
      ${
        task.result_json
          ? `<div><p class="panel-kicker">Parsed Result JSON</p><pre class="raw-json">${escapeHtml(
              JSON.stringify(task.result_json, null, 2),
            )}</pre></div>`
          : ""
      }
    </div>
  `;

  $("#task-detail").querySelectorAll("[data-open-report]").forEach((button) => {
    button.addEventListener("click", async () => {
      switchSection("reports");
      await selectReport(button.dataset.openReport);
    });
  });
}

function buildMetricCards(metrics) {
  if (!metrics) return "";
  const keys = [
    ["sharpe", "Sharpe", false],
    ["cagr", "CAGR", true],
    ["max_dd", "Max DD", true],
    ["calmar", "Calmar", false],
    ["annual_vol", "Annual Vol", true],
    ["avg_turnover", "Avg Turnover", false],
    ["avg_active_positions", "Avg Positions", false],
    ["trade_count", "Trade Count", false],
  ];
  return `
    <div class="summary-grid">
      ${keys
        .filter(([key]) => metrics[key] !== undefined)
        .map(
          ([key, label, isPercent]) => `
            <div class="summary-card">
              <div class="panel-kicker">${label}</div>
              <span class="value">${isPercent ? formatPercent(metrics[key]) : formatNumber(metrics[key])}</span>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function buildSimpleTable(rows, columns) {
  if (!rows || !rows.length) return `<p class="empty-state">暂无表格数据。</p>`;
  return `
    <div class="table-wrap">
      <table>
        <thead><tr>${columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("")}</tr></thead>
        <tbody>
          ${rows
            .map(
              (row) => `
                <tr>
                  ${columns
                    .map((column) => {
                      const raw = row[column.key];
                      const value =
                        column.format === "percent"
                          ? formatPercent(raw)
                          : column.format === "number"
                            ? formatNumber(raw)
                            : raw ?? "N/A";
                      return `<td>${escapeHtml(String(value))}</td>`;
                    })
                    .join("")}
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderFactorPipeline(report) {
  const selection = report.selection || {};
  const composite = report.composite_oos || {};
  const walkForward = report.walk_forward || {};
  return `
    <div class="section-stack">
      <div class="tag-list">${(selection.stable_factors || []).map((factor) => `<span class="tag">${escapeHtml(factor)}</span>`).join("")}</div>
      ${buildMetricCards(composite.metrics)}
      <div class="split-grid">
        <div class="note-box">
          <p class="panel-kicker">稳定因子</p>
          <div>${(selection.stable_factors || []).map((factor) => `<span class="chip">${escapeHtml(factor)}</span>`).join(" ") || "暂无"}</div>
          <div class="pill-row">${(composite.latest_picks || []).slice(0, 10).map((pick) => `<span class="pill">${escapeHtml(pick)}</span>`).join("")}</div>
        </div>
        <div class="note-box">
          <p class="panel-kicker">Walk-Forward 摘要</p>
          <div>窗口数: ${formatNumber(walkForward.window_summary?.window_count ?? 0, 0)}</div>
          <div>正 Sharpe 占比: ${formatPercent(walkForward.window_summary?.positive_sharpe_ratio ?? 0)}</div>
          <div>中位 Sharpe: ${formatNumber(walkForward.window_summary?.median_sharpe ?? 0)}</div>
          <div>最差窗口 Max DD: ${formatPercent(walkForward.window_summary?.worst_window_max_dd ?? 0)}</div>
        </div>
      </div>
      <div>
        <p class="panel-kicker">排名靠前的因子</p>
        ${buildSimpleTable(selection.ranked_factors || [], [
          { key: "factor", label: "因子" },
          { key: "train_rank_ic", label: "Train Rank IC", format: "number" },
          { key: "train_hit_rate", label: "Train Hit Rate", format: "percent" },
          { key: "selection_score", label: "Score", format: "number" },
        ])}
      </div>
    </div>
  `;
}

function renderComboSearch(report) {
  const best = report.best_combination || {};
  return `
    <div class="section-stack">
      <div class="tag-list">${(best.factors || []).map((factor) => `<span class="tag">${escapeHtml(factor)}</span>`).join("")}</div>
      <div class="split-grid">
        <div><p class="panel-kicker">Train Metrics</p>${buildMetricCards(best.train_metrics)}</div>
        <div><p class="panel-kicker">OOS Metrics</p>${buildMetricCards(best.oos_metrics)}</div>
      </div>
      <div class="note-box">
        <p class="panel-kicker">组合摘要</p>
        <div>最大两两相关性: ${formatNumber(best.max_abs_corr)}</div>
        <div>研究分数: ${formatNumber(best.research_score)}</div>
        <div>稳定性分数: ${formatNumber(best.stability_score)}</div>
        <div>Train 最新持仓: ${(best.train_latest_picks || []).join(", ") || "N/A"}</div>
        <div>OOS 最新持仓: ${(best.oos_latest_picks || []).join(", ") || "N/A"}</div>
      </div>
      <div>
        <p class="panel-kicker">因子明细</p>
        ${buildSimpleTable(best.factor_details || [], [
          { key: "factor", label: "因子" },
          { key: "direction_label", label: "方向" },
          { key: "train_rank_ic", label: "Train Rank IC", format: "number" },
          { key: "oos_rank_ic", label: "OOS Rank IC", format: "number" },
          { key: "selection_score", label: "Score", format: "number" },
        ])}
      </div>
    </div>
  `;
}

function renderComboWalkForward(report) {
  return `
    <div class="section-stack">
      <div class="summary-grid">
        <div class="summary-card"><div class="panel-kicker">窗口数</div><span class="value">${formatNumber(report.window_summary?.window_count ?? 0, 0)}</span></div>
        <div class="summary-card"><div class="panel-kicker">正 Sharpe 占比</div><span class="value">${formatPercent(report.window_summary?.positive_test_sharpe_ratio ?? 0)}</span></div>
        <div class="summary-card"><div class="panel-kicker">中位 Sharpe</div><span class="value">${formatNumber(report.window_summary?.median_test_sharpe ?? 0)}</span></div>
        <div class="summary-card"><div class="panel-kicker">最差 Max DD</div><span class="value">${formatPercent(report.window_summary?.worst_test_max_dd ?? 0)}</span></div>
      </div>
      <div class="note-box">
        <p class="panel-kicker">最佳窗口</p>
        <div>训练窗: ${(report.best_window?.train_window || []).join(" -> ") || "N/A"}</div>
        <div>测试窗: ${(report.best_window?.test_window || []).join(" -> ") || "N/A"}</div>
        <div>组合: ${(report.best_window?.selected_combo?.factors || []).join(", ") || "N/A"}</div>
      </div>
      <div>
        <p class="panel-kicker">组合出现频率</p>
        ${buildSimpleTable(
          Object.entries(report.selected_combo_frequency || {}).map(([combo, count]) => ({ combo, count })),
          [
            { key: "combo", label: "组合" },
            { key: "count", label: "次数", format: "number" },
          ],
        )}
      </div>
    </div>
  `;
}

function renderRiskSearch(report) {
  const combo = report.base_combo?.best_combination || report.best_combination || {};
  const best = report.best_candidate || {};
  return `
    <div class="section-stack">
      <div class="tag-list">${(combo.factors || []).map((factor) => `<span class="tag">${escapeHtml(factor)}</span>`).join("")}</div>
      <div class="note-box">
        <p class="panel-kicker">最佳风控参数</p>
        <pre class="raw-json">${escapeHtml(JSON.stringify(best.risk_overrides || {}, null, 2))}</pre>
      </div>
      <div class="split-grid">
        <div><p class="panel-kicker">Train Metrics</p>${buildMetricCards(best.train_metrics)}</div>
        <div><p class="panel-kicker">OOS Metrics</p>${buildMetricCards(best.oos_metrics)}</div>
      </div>
      <div>
        <p class="panel-kicker">Top Candidates</p>
        ${buildSimpleTable((report.top_candidates || []).slice(0, 8).map((row) => ({
          gross_exposure: row.risk_overrides?.gross_exposure,
          stop_loss_pct: row.risk_overrides?.stop_loss_pct,
          trailing_stop_atr_multiple: row.risk_overrides?.trailing_stop_atr_multiple,
          max_holding_days: row.risk_overrides?.max_holding_days,
          top_n: row.risk_overrides?.top_n,
          oos_sharpe: row.oos_metrics?.sharpe,
          oos_max_dd: row.oos_metrics?.max_dd,
        })), [
          { key: "gross_exposure", label: "Gross Exposure", format: "number" },
          { key: "stop_loss_pct", label: "Stop Loss", format: "percent" },
          { key: "trailing_stop_atr_multiple", label: "ATR Stop", format: "number" },
          { key: "max_holding_days", label: "Hold Days", format: "number" },
          { key: "top_n", label: "Top N", format: "number" },
          { key: "oos_sharpe", label: "OOS Sharpe", format: "number" },
          { key: "oos_max_dd", label: "OOS Max DD", format: "percent" },
        ])}
      </div>
    </div>
  `;
}

function renderGenericReport(report) {
  return `
    <div class="section-stack">
      <div class="summary-grid">
        <div class="summary-card"><div class="panel-kicker">Generated</div><span class="value">${escapeHtml(formatDateText(report.generated_at_utc))}</span></div>
        <div class="summary-card"><div class="panel-kicker">Top Keys</div><span class="value">${Object.keys(report).length}</span></div>
      </div>
      <pre class="raw-json">${escapeHtml(JSON.stringify(report, null, 2))}</pre>
    </div>
  `;
}

async function renderSelectedReport() {
  const container = $("#report-content");
  if (!state.selectedReport) {
    container.innerHTML = `<p class="empty-state">从左侧选择一份 JSON 报告，页面会自动抽取关键指标和摘要。</p>`;
    return;
  }

  const { content } = state.selectedReport;
  $("#report-title").textContent = state.selectedReport.name;

  let summary = "";
  if (content.best_candidate) summary = renderRiskSearch(content);
  else if (content.best_combination) summary = renderComboSearch(content);
  else if (content.selection && content.composite_oos) summary = renderFactorPipeline(content);
  else if (content.window_summary && content.best_window) summary = renderComboWalkForward(content);
  else summary = renderGenericReport(content);

  const markdownName = state.reports.find((report) => report.name === state.selectedReport.name)?.markdown_name;
  let markdownBlock = "";
  if (markdownName) {
    try {
      const response = await fetch(`/api/report?name=${encodeURIComponent(markdownName)}`);
      const payload = await response.json();
      if (payload.content_type === "markdown") {
        markdownBlock = `<div><p class="panel-kicker">Markdown 摘要</p><div class="markdown-box">${escapeHtml(payload.content)}</div></div>`;
      }
    } catch (error) {
      markdownBlock = "";
    }
  }

  container.innerHTML = `
    ${summary}
    ${markdownBlock}
    <div>
      <p class="panel-kicker">Raw JSON</p>
      <pre class="raw-json">${escapeHtml(JSON.stringify(content, null, 2))}</pre>
    </div>
  `;
}

function renderReportList() {
  $("#report-list").innerHTML = state.reports.length
    ? state.reports
        .map(
          (report) => `
            <button class="report-item ${state.selectedReport?.name === report.name ? "active" : ""}" data-report="${report.name}">
              <p class="panel-kicker">${escapeHtml(report.name.replace(".json", ""))}</p>
              <div>${escapeHtml(formatDateText(report.mtime))}</div>
              <div class="muted">${report.has_markdown ? "含 Markdown 摘要" : "仅 JSON"}</div>
            </button>
          `,
        )
        .join("")
    : `<p class="empty-state">还没有发现报告文件。</p>`;

  document.querySelectorAll("[data-report]").forEach((button) => {
    button.addEventListener("click", async () => {
      await selectReport(button.dataset.report);
    });
  });
}

async function selectReport(name) {
  const response = await fetch(`/api/report?name=${encodeURIComponent(name)}`);
  const payload = await response.json();
  if (!response.ok) {
    alert(payload.error || "读取报告失败");
    return;
  }
  state.selectedReport = payload;
  renderReportList();
  await renderSelectedReport();
}

async function fetchMeta() {
  const response = await fetch("/api/meta");
  const payload = await response.json();
  state.meta = payload;
  $("#python-badge").textContent = payload.python_executable;
  renderOverview();
  renderWorkflowList();
  renderWorkflowForm();
}

async function fetchReports() {
  const response = await fetch("/api/reports");
  const payload = await response.json();
  state.reports = payload.items || [];
  renderOverview();
  renderReportList();
  if (!state.selectedReport && state.reports[0]) await selectReport(state.reports[0].name);
}

async function fetchTasks() {
  const response = await fetch("/api/tasks");
  const payload = await response.json();
  state.tasks = payload.items || [];
  renderTasks();
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const payload = await response.json();
    if (payload.ok) {
      $("#health-dot").className = "status-dot online";
      $("#health-text").textContent = "本地服务在线";
      return;
    }
  } catch (error) {
    // ignore
  }
  $("#health-dot").className = "status-dot offline";
  $("#health-text").textContent = "服务未连接";
}

async function submitTask(event) {
  event.preventDefault();
  const workflow = state.selectedWorkflow;
  const params = { ...state.formValues };

  ["gross_exposure_grid", "top_n_grid", "stop_loss_grid", "trailing_stop_grid", "max_holding_days_grid"].forEach((key) => {
    if (params[key] !== undefined && typeof params[key] === "string") params[key] = parseListInput(params[key], true);
  });

  const response = await fetch("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workflow, params }),
  });
  const payload = await response.json();
  if (!response.ok) {
    alert(payload.error || "启动任务失败");
    return;
  }
  switchSection("lab");
  state.activeTaskId = payload.id;
  await fetchTasks();
}

function bindActions() {
  $("#workflow-form").addEventListener("submit", submitTask);
  $("#reset-form").addEventListener("click", () => {
    resetWorkflowValues(state.selectedWorkflow);
    renderWorkflowForm();
  });
  $("#refresh-all").addEventListener("click", bootstrapData);
  $("#open-default-workflow").addEventListener("click", () => {
    switchSection("lab");
    selectWorkflow("factor-pipeline");
  });
  $("#jump-to-reports").addEventListener("click", () => switchSection("reports"));
}

async function bootstrapData() {
  await checkHealth();
  await fetchMeta();
  await fetchReports();
  await fetchTasks();
}

async function init() {
  renderNav();
  bindActions();
  resetWorkflowValues(state.selectedWorkflow);
  await bootstrapData();
  setInterval(fetchTasks, 2500);
  setInterval(fetchReports, 12000);
}

init();
