const CAPACITY_LIMIT = 17;

const state = {
  session: null,
  records: [],
};

const loginPanel = document.getElementById("loginPanel");
const dashboard = document.getElementById("dashboard");
const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");
const loginError = document.getElementById("loginError");
const registerMessage = document.getElementById("registerMessage");
const sessionBadge = document.getElementById("sessionBadge");
const logoutBtn = document.getElementById("logoutBtn");
const tripForm = document.getElementById("tripForm");
const formStatus = document.getElementById("formStatus");
const clearFormBtn = document.getElementById("clearFormBtn");
const recordsTableBody = document.getElementById("recordsTableBody");
const travelSummary = document.getElementById("travelSummary");
const printDriverLogBtn = document.getElementById("printDriverLogBtn");
const printRequestsBtn = document.getElementById("printRequestsBtn");
const clearDataBtn = document.getElementById("clearDataBtn");
const ticketSheet = document.getElementById("ticketSheet");
const driverLogSheet = document.getElementById("driverLogSheet");
const requestSheet = document.getElementById("requestSheet");

const fieldRefs = {
  requestId: document.getElementById("requestId"),
  passengerName: document.getElementById("passengerName"),
  residence: document.getElementById("residence"),
  companionName: document.getElementById("companionName"),
  destination: document.getElementById("destination"),
  tripDate: document.getElementById("tripDate"),
  tripTime: document.getElementById("tripTime"),
  driverName: document.getElementById("driverName"),
  unitNumber: document.getElementById("unitNumber"),
  contactPhone: document.getElementById("contactPhone"),
  notes: document.getElementById("notes"),
};

function showStatus(element, message, type) {
  element.textContent = message;
  element.classList.remove("status-success", "status-error");
  if (type) {
    element.classList.add(type === "error" ? "status-error" : "status-success");
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    method: options.method || "GET",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    credentials: "same-origin",
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  const rawText = await response.text();
  let data = {};

  if (rawText) {
    try {
      data = JSON.parse(rawText);
    } catch {
      data = { rawText };
    }
  }

  if (!response.ok) {
    throw new Error(data.error || data.rawText || `Error HTTP ${response.status}`);
  }
  return data;
}

function formatDate(dateString) {
  if (!dateString) return "";
  return new Date(`${dateString}T00:00:00`).toLocaleDateString("es-MX", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function formatDateTime(record) {
  return `${formatDate(record.trip_date || record.tripDate)} | ${record.trip_time || record.tripTime} h`;
}

function getTripKey(record) {
  const destination = record.destination;
  const tripDate = record.trip_date || record.tripDate;
  const tripTime = record.trip_time || record.tripTime;
  return `${destination}__${tripDate}__${tripTime}`;
}

function getGroupedTrips(records) {
  return records.reduce((acc, record) => {
    const key = getTripKey(record);
    if (!acc[key]) {
      acc[key] = [];
    }
    acc[key].push(record);
    return acc;
  }, {});
}

function getTripOccupancy(records, record) {
  const tripDate = record.trip_date || record.tripDate;
  const tripTime = record.trip_time || record.tripTime;
  return records.filter((item) => (
    item.destination === record.destination &&
    (item.trip_date || item.tripDate) === tripDate &&
    (item.trip_time || item.tripTime) === tripTime
  )).length;
}

function normalizeRecordForPrint(record) {
  return {
    id: record.id,
    requestId: record.request_id || record.requestId,
    passengerName: record.passenger_name || record.passengerName,
    residence: record.residencia || record.residence,
    companionName: record.companion_name || record.companionName,
    destination: record.destination,
    tripDate: record.trip_date || record.tripDate,
    tripTime: record.trip_time || record.tripTime,
    driverName: record.driver_name || record.driverName,
    unitNumber: record.unit_number || record.unitNumber,
    contactPhone: record.contact_phone || record.contactPhone,
    notes: record.notes,
    createdAt: record.created_at || record.createdAt,
    createdByName: record.created_by_name || record.createdByName,
  };
}

function toggleApp() {
  const isLoggedIn = Boolean(state.session);
  loginPanel.classList.toggle("hidden", isLoggedIn);
  dashboard.classList.toggle("hidden", !isLoggedIn);
  sessionBadge.textContent = isLoggedIn
    ? `${state.session.fullName} | ${state.session.role}`
    : "";
}

function resetForm() {
  tripForm.reset();
  fieldRefs.requestId.value = `SOL-${new Date().getFullYear()}-${String(state.records.length + 1).padStart(3, "0")}`;
  fieldRefs.tripDate.min = new Date().toISOString().split("T")[0];
}

function renderSummary() {
  const groupedTrips = Object.values(getGroupedTrips(state.records));

  if (!groupedTrips.length) {
    travelSummary.innerHTML = '<div class="summary-card"><strong>Sin viajes programados</strong><p>Cuando registres pasajeros, aqui veras el cupo disponible por salida.</p></div>';
    return;
  }

  travelSummary.innerHTML = groupedTrips
    .sort((a, b) => `${a[0].trip_date}${a[0].trip_time}`.localeCompare(`${b[0].trip_date}${b[0].trip_time}`))
    .map((group) => {
      const trip = group[0];
      const occupancy = group.length;
      const remaining = CAPACITY_LIMIT - occupancy;
      return `
        <div class="summary-card">
          <strong>${trip.destination}</strong>
          <p>${formatDate(trip.trip_date)} | ${trip.trip_time} h</p>
          <span class="capacity-pill ${remaining <= 0 ? "capacity-full" : "capacity-ok"}">
            ${occupancy}/${CAPACITY_LIMIT} personas
          </span>
          <p>${remaining > 0 ? `${remaining} lugares disponibles` : "Cupo lleno"}</p>
        </div>
      `;
    })
    .join("");
}

function renderTable() {
  if (!state.records.length) {
    recordsTableBody.innerHTML = '<tr><td colspan="9">No hay pasajeros registrados todavia.</td></tr>';
    return;
  }
  const canDelete = state.session?.role === "administrador";

  recordsTableBody.innerHTML = state.records
    .map((record) => {
      const occupancy = getTripOccupancy(state.records, record);
      return `
        <tr>
          <td>${record.request_id}</td>
          <td>${record.passenger_name}</td>
          <td>${record.destination}</td>
          <td>${formatDate(record.trip_date)}</td>
          <td>${record.trip_time}</td>
          <td>${record.driver_name}</td>
          <td>${record.created_by_name}</td>
          <td>${occupancy}/${CAPACITY_LIMIT}</td>
          <td>
            <div class="inline-actions">
              <button type="button" data-action="ticket" data-id="${record.id}" class="secondary-btn">Ticket</button>
              <button type="button" data-action="request" data-id="${record.id}" class="secondary-btn">Solicitud</button>
              ${canDelete ? `<button type="button" data-action="delete" data-id="${record.id}" class="ghost-btn">Eliminar</button>` : ""}
            </div>
          </td>
        </tr>
      `;
    })
    .join("");
}

function printSheet(targetSheet) {
  [ticketSheet, driverLogSheet, requestSheet].forEach((sheet) => {
    sheet.classList.remove("active-print");
  });
  targetSheet.classList.add("active-print");
  window.print();
  targetSheet.classList.remove("active-print");
}

function renderTicket(rawRecord) {
  const record = normalizeRecordForPrint(rawRecord);
  ticketSheet.innerHTML = `
    <div class="document">
      <h1>Ticket de viaje</h1>
      <div class="document-grid">
        <div class="document-block"><strong>Folio:</strong><br>${record.requestId}</div>
        <div class="document-block"><strong>Fecha de emision:</strong><br>${new Date(record.createdAt).toLocaleString("es-MX")}</div>
        <div class="document-block"><strong>Paciente:</strong><br>${record.passengerName}</div>
        <div class="document-block"><strong>Residencia:</strong><br>${record.residence}</div>
        <div class="document-block"><strong>Destino:</strong><br>${record.destination}</div>
        <div class="document-block"><strong>Salida:</strong><br>${formatDateTime(record)}</div>
        <div class="document-block"><strong>Chofer:</strong><br>${record.driverName}</div>
        <div class="document-block"><strong>Unidad:</strong><br>${record.unitNumber}</div>
      </div>
      <div class="document-block">
        <strong>Contacto:</strong> ${record.contactPhone}<br>
        <strong>Acompanante:</strong> ${record.companionName || "No registrado"}<br>
        <strong>Capturo:</strong> ${record.createdByName || "-"}<br>
        <strong>Observaciones:</strong> ${record.notes || "Sin observaciones"}
      </div>
      <p>Presentar este ticket al abordar la ambulancia.</p>
    </div>
  `;
}

function renderRequest(rawRecord) {
  const record = normalizeRecordForPrint(rawRecord);
  requestSheet.innerHTML = `
    <div class="document">
      <h1>Solicitud de traslado</h1>
      <h3>${record.requestId}</h3>
      <p>Documento generado para la elaboracion y control de solicitudes de viaje.</p>
      <div class="document-grid">
        <div class="document-block"><strong>Paciente</strong><br>${record.passengerName}</div>
        <div class="document-block"><strong>Residencia</strong><br>${record.residence}</div>
        <div class="document-block"><strong>Destino solicitado</strong><br>${record.destination}</div>
        <div class="document-block"><strong>Fecha y hora</strong><br>${formatDateTime(record)}</div>
        <div class="document-block"><strong>Chofer asignado</strong><br>${record.driverName}</div>
        <div class="document-block"><strong>Unidad</strong><br>${record.unitNumber}</div>
        <div class="document-block"><strong>Telefono</strong><br>${record.contactPhone}</div>
        <div class="document-block"><strong>Acompanante</strong><br>${record.companionName || "No aplica"}</div>
      </div>
      <div class="document-block">
        <strong>Motivo del traslado</strong>
        <p>${record.notes || "No se registraron observaciones."}</p>
      </div>
      <div class="document-grid">
        <div class="document-block"><strong>Solicita</strong><br><br>________________________</div>
        <div class="document-block"><strong>Autoriza</strong><br><br>________________________</div>
      </div>
    </div>
  `;
}

function renderDriverLog() {
  const groups = Object.values(getGroupedTrips(state.records));

  driverLogSheet.innerHTML = `
    <div class="document">
      <h1>Bitacora de viajes del chofer</h1>
      <p>Fecha de impresion: ${new Date().toLocaleString("es-MX")}</p>
      ${
        groups.length
          ? groups
              .sort((a, b) => `${a[0].trip_date}${a[0].trip_time}`.localeCompare(`${b[0].trip_date}${b[0].trip_time}`))
              .map((group) => `
                <section>
                  <h2>${group[0].destination} | ${formatDate(group[0].trip_date)} | ${group[0].trip_time} h</h2>
                  <p>Chofer: ${group[0].driver_name} | Unidad: ${group[0].unit_number} | Pasajeros: ${group.length}/${CAPACITY_LIMIT}</p>
                  <table>
                    <thead>
                      <tr>
                        <th>Folio</th>
                        <th>Paciente</th>
                        <th>Residencia</th>
                        <th>Acompanante</th>
                        <th>Telefono</th>
                        <th>Capturo</th>
                        <th>Observaciones</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${group.map((record) => `
                        <tr>
                          <td>${record.request_id}</td>
                          <td>${record.passenger_name}</td>
                          <td>${record.residencia}</td>
                          <td>${record.companion_name || "No"}</td>
                          <td>${record.contact_phone}</td>
                          <td>${record.created_by_name}</td>
                          <td>${record.notes || "Sin observaciones"}</td>
                        </tr>
                      `).join("")}
                    </tbody>
                  </table>
                </section>
              `)
              .join("")
          : "<p>No existen viajes registrados.</p>"
      }
    </div>
  `;
}

function renderRequestsSummary() {
  requestSheet.innerHTML = `
    <div class="document">
      <h1>Solicitudes generadas</h1>
      <p>Total de solicitudes: ${state.records.length}</p>
      <table>
        <thead>
          <tr>
            <th>Folio</th>
            <th>Paciente</th>
            <th>Destino</th>
            <th>Fecha</th>
            <th>Hora</th>
            <th>Chofer</th>
            <th>Capturo</th>
          </tr>
        </thead>
        <tbody>
          ${
            state.records.length
              ? state.records.map((record) => `
                <tr>
                  <td>${record.request_id}</td>
                  <td>${record.passenger_name}</td>
                  <td>${record.destination}</td>
                  <td>${formatDate(record.trip_date)}</td>
                  <td>${record.trip_time}</td>
                  <td>${record.driver_name}</td>
                  <td>${record.created_by_name}</td>
                </tr>
              `).join("")
              : '<tr><td colspan="7">No hay solicitudes registradas.</td></tr>'
          }
        </tbody>
      </table>
    </div>
  `;
}

function renderAll() {
  toggleApp();
  renderSummary();
  renderTable();
  resetForm();
}

async function loadTrips() {
  const data = await api("/api/trips");
  state.records = data.records;
  renderAll();
}

function buildRecordPayload() {
  return {
    requestId: fieldRefs.requestId.value.trim(),
    passengerName: fieldRefs.passengerName.value.trim(),
    residence: fieldRefs.residence.value.trim(),
    companionName: fieldRefs.companionName.value.trim(),
    destination: fieldRefs.destination.value,
    tripDate: fieldRefs.tripDate.value,
    tripTime: fieldRefs.tripTime.value,
    driverName: fieldRefs.driverName.value.trim(),
    unitNumber: fieldRefs.unitNumber.value.trim(),
    contactPhone: fieldRefs.contactPhone.value.trim(),
    notes: fieldRefs.notes.value.trim(),
  };
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await api("/api/auth/login", {
      method: "POST",
      body: {
        username: document.getElementById("username").value.trim(),
        password: document.getElementById("password").value,
      },
    });
    state.session = result.user;
    showStatus(loginError, "", null);
    toggleApp();
    try {
      await loadTrips();
    } catch (error) {
      state.session = null;
    toggleApp();
    }
  } catch (error) {
    showStatus(loginError, error.message, "error");
  }
});

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await api("/api/auth/register", {
      method: "POST",
      body: {
        fullName: document.getElementById("registerFullName").value.trim(),
        username: document.getElementById("registerUsername").value.trim(),
        password: document.getElementById("registerPassword").value,
      },
    });
    state.session = result.user;
    registerForm.reset();
    showStatus(registerMessage, "Usuario creado y sesion iniciada.", "success");
    toggleApp();
    try {
      await loadTrips();
    } catch (error) {
      showStatus(formStatus, `Usuario creado, pero no se pudo cargar la agenda: ${error.message}`, "error");
    }
  } catch (error) {
    showStatus(registerMessage, error.message, "error");
  }
});

logoutBtn.addEventListener("click", async () => {
  try {
    await api("/api/auth/logout", { method: "POST", body: {} });
  } catch (error) {
    console.error(error);
  }
  state.session = null;
  state.records = [];
  toggleApp();
});

clearFormBtn.addEventListener("click", () => {
  resetForm();
  showStatus(formStatus, "", null);
});

tripForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await api("/api/trips", {
      method: "POST",
      body: buildRecordPayload(),
    });
    showStatus(formStatus, `Registro guardado. Lugar asignado ${result.occupancy} de ${CAPACITY_LIMIT}.`, "success");
    await loadTrips();
    renderTicket(result.record);
  } catch (error) {
    showStatus(formStatus, error.message, "error");
  }
});

recordsTableBody.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;

  const { action, id } = button.dataset;
  const record = state.records.find((item) => String(item.id) === id);
  if (!record) return;

  if (action === "ticket") {
    renderTicket(record);
    printSheet(ticketSheet);
    return;
  }

  if (action === "request") {
    renderRequest(record);
    printSheet(requestSheet);
    return;
  }

  if (action === "delete") {
    try {
      await api(`/api/trips/${id}`, { method: "DELETE" });
      showStatus(formStatus, "Registro eliminado de la agenda.", "success");
      await loadTrips();
    } catch (error) {
      showStatus(formStatus, error.message, "error");
    }
  }
});

printDriverLogBtn.addEventListener("click", () => {
  renderDriverLog();
  printSheet(driverLogSheet);
});

printRequestsBtn.addEventListener("click", () => {
  renderRequestsSummary();
  printSheet(requestSheet);
});

clearDataBtn.addEventListener("click", () => {
  showStatus(formStatus, "La agenda ahora se gestiona desde la base de datos. Elimina los registros uno por uno o puedo agregarte una limpieza administrativa despues.", "error");
});

async function bootstrap() {
  resetForm();
  try {
    const result = await api("/api/auth/session");
    state.session = result.user;
    await loadTrips();
  } catch (error) {
    state.session = null;
    state.records = [];
    toggleApp();
  }
}

bootstrap();
