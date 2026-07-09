const { getStore } = require("@netlify/blobs");

const STORE_NAME = "tramites-iprus";
const STORE_KEY = "shared-state";
const DEFAULT_TITLE = "TRAMITES IPRUS SHARED STATE";

function resolveStore() {
  const siteID = process.env.NETLIFY_SITE_ID || process.env.SITE_ID || "";
  const token = process.env.NETLIFY_AUTH_TOKEN || process.env.NETLIFY_API_TOKEN || "";

  if (siteID && token) {
    return getStore(STORE_NAME, { siteID, token });
  }

  return getStore(STORE_NAME);
}

function sanitizeAssignments(rawAssignments) {
  if (!rawAssignments || typeof rawAssignments !== "object") {
    return {};
  }

  const assignments = {};
  Object.entries(rawAssignments).forEach(([recordId, assignee]) => {
    const normalizedRecordId = String(recordId || "").trim();
    const normalizedAssignee = String(assignee || "").trim();
    if (normalizedRecordId && normalizedAssignee) {
      assignments[normalizedRecordId] = normalizedAssignee;
    }
  });

  return assignments;
}

function sanitizeReviewResults(rawReviewResults) {
  if (!rawReviewResults || typeof rawReviewResults !== "object") {
    return {};
  }

  const sanitizedReviewResults = {};
  Object.entries(rawReviewResults).forEach(([recordId, rawRecordReview]) => {
    const normalizedRecordId = String(recordId || "").trim();
    if (!normalizedRecordId || !rawRecordReview || typeof rawRecordReview !== "object") {
      return;
    }

    const nextRecordReview = {};
    Object.entries(rawRecordReview).forEach(([fieldKey, value]) => {
      const normalizedFieldKey = String(fieldKey || "").trim();
      if (!normalizedFieldKey) {
        return;
      }

      if (normalizedFieldKey.endsWith("__note")) {
        const normalizedNote = String(value || "").trim();
        if (normalizedNote) {
          nextRecordReview[normalizedFieldKey] = normalizedNote;
        }
        return;
      }

      if (value === "si" || value === "no") {
        nextRecordReview[normalizedFieldKey] = value;
      }
    });

    if (Object.keys(nextRecordReview).length) {
      sanitizedReviewResults[normalizedRecordId] = nextRecordReview;
    }
  });

  return sanitizedReviewResults;
}

function sanitizeEvidenceImages(rawEvidenceImages) {
  if (!rawEvidenceImages || typeof rawEvidenceImages !== "object") {
    return {};
  }

  const sanitizedEvidenceImages = {};
  Object.entries(rawEvidenceImages).forEach(([recordId, rawImages]) => {
    const normalizedRecordId = String(recordId || "").trim();
    if (!normalizedRecordId || !Array.isArray(rawImages)) {
      return;
    }

    const images = rawImages
      .map((rawImage) => {
        if (!rawImage || typeof rawImage !== "object") {
          return null;
        }

        const id = String(rawImage.id || "").trim();
        const name = String(rawImage.name || "").trim() || "evidencia";
        const dataUrl = String(rawImage.dataUrl || "").trim();
        if (!id || !dataUrl.startsWith("data:image/")) {
          return null;
        }

        return { id, name, dataUrl };
      })
      .filter(Boolean);

    if (images.length) {
      sanitizedEvidenceImages[normalizedRecordId] = images;
    }
  });

  return sanitizedEvidenceImages;
}

function sanitizeReportDrafts(rawDrafts) {
  if (!rawDrafts || typeof rawDrafts !== "object") {
    return {};
  }

  const sanitizedDrafts = {};
  Object.entries(rawDrafts).forEach(([recordId, rawDraft]) => {
    const normalizedRecordId = String(recordId || "").trim();
    if (!normalizedRecordId || !rawDraft || typeof rawDraft !== "object") {
      return;
    }

    const nextDraft = {};
    ["antecedente", "analisis", "observaciones", "conclusion"].forEach((fieldKey) => {
      const value = typeof rawDraft[fieldKey] === "string" ? rawDraft[fieldKey].replace(/\r/g, "").trim() : "";
      if (value) {
        nextDraft[fieldKey] = value;
      }
    });

    const updatedAt = typeof rawDraft.updatedAt === "string" ? rawDraft.updatedAt.trim() : "";
    const updatedBy = typeof rawDraft.updatedBy === "string" ? rawDraft.updatedBy.trim() : "";
    if (updatedAt) {
      nextDraft.updatedAt = updatedAt;
    }
    if (updatedBy) {
      nextDraft.updatedBy = updatedBy;
    }

    if (Object.keys(nextDraft).length) {
      sanitizedDrafts[normalizedRecordId] = nextDraft;
    }
  });

  return sanitizedDrafts;
}

function normalizeTaskStatus(value) {
  if (value === "en_proceso" || value === "completada") {
    return value;
  }
  return "pendiente";
}

function sanitizeTaskQueue(rawTasks) {
  if (!Array.isArray(rawTasks)) {
    return [];
  }

  return rawTasks
    .map((rawTask) => {
      if (!rawTask || typeof rawTask !== "object") {
        return null;
      }

      const id = String(rawTask.id || "").trim();
      const recordId = String(rawTask.recordId || "").trim();
      const title = String(rawTask.title || "").trim();
      const notes = String(rawTask.notes || "").replace(/\r/g, "").trim();
      const assignee = String(rawTask.assignee || "").trim();
      const createdBy = String(rawTask.createdBy || "").trim();
      const updatedBy = String(rawTask.updatedBy || "").trim();
      const createdAt = String(rawTask.createdAt || "").trim();
      const updatedAt = String(rawTask.updatedAt || "").trim();
      const status = normalizeTaskStatus(rawTask.status);

      if (!id || !recordId || !title) {
        return null;
      }

      return {
        id,
        recordId,
        title,
        notes,
        assignee,
        status,
        createdBy,
        updatedBy,
        createdAt,
        updatedAt,
      };
    })
    .filter(Boolean)
    .sort((left, right) => String(right.updatedAt || right.createdAt || "").localeCompare(String(left.updatedAt || left.createdAt || "")));
}

function sanitizeActivityLog(rawEntries) {
  if (!Array.isArray(rawEntries)) {
    return [];
  }

  return rawEntries
    .map((rawEntry) => {
      if (!rawEntry || typeof rawEntry !== "object") {
        return null;
      }

      const id = String(rawEntry.id || "").trim();
      const recordId = String(rawEntry.recordId || "").trim();
      const actor = String(rawEntry.actor || "").trim();
      const actorMode = String(rawEntry.actorMode || "").trim();
      const actionType = String(rawEntry.actionType || "").trim();
      const fieldKey = String(rawEntry.fieldKey || "").trim();
      const summary = String(rawEntry.summary || "").trim();
      const detail = String(rawEntry.detail || "").replace(/\r/g, "").trim();
      const timestamp = String(rawEntry.timestamp || "").trim();
      const recordCode = String(rawEntry.recordCode || "").trim();
      const tramiteNumber = String(rawEntry.tramiteNumber || "").trim();

      if (!id || !recordId || !summary || !timestamp) {
        return null;
      }

      return {
        id,
        recordId,
        actor,
        actorMode,
        actionType,
        fieldKey,
        summary,
        detail,
        timestamp,
        recordCode,
        tramiteNumber,
      };
    })
    .filter(Boolean)
    .sort((left, right) => String(right.timestamp).localeCompare(String(left.timestamp)))
    .slice(0, 800);
}

function mergeObjectMaps(baseMap, overlayMap) {
  return {
    ...(baseMap || {}),
    ...(overlayMap || {}),
  };
}

function mergeArrayById(baseItems, overlayItems) {
  const itemMap = new Map();
  (baseItems || []).forEach((item) => {
    itemMap.set(item.id, item);
  });
  (overlayItems || []).forEach((item) => {
    itemMap.set(item.id, item);
  });
  return [...itemMap.values()];
}

function buildPayload(rawPayload) {
  const payload = rawPayload && typeof rawPayload === "object" ? rawPayload : {};
  return {
    title: typeof payload.title === "string" && payload.title.trim() ? payload.title.trim() : DEFAULT_TITLE,
    sourceDate: typeof payload.sourceDate === "string" ? payload.sourceDate : "",
    generatedAt: new Date().toISOString(),
    assignments: sanitizeAssignments(payload.assignments),
    reviewResults: sanitizeReviewResults(payload.reviewResults),
    evidenceImages: sanitizeEvidenceImages(payload.evidenceImages),
    reportDrafts: sanitizeReportDrafts(payload.reportDrafts),
    taskQueue: sanitizeTaskQueue(payload.taskQueue),
    activityLog: sanitizeActivityLog(payload.activityLog),
  };
}

function mergePayloads(basePayload, overlayPayload) {
  const base = buildPayload(basePayload);
  const overlay = buildPayload(overlayPayload);
  return {
    title: overlay.title || base.title || DEFAULT_TITLE,
    sourceDate: overlay.sourceDate || base.sourceDate || "",
    generatedAt: new Date().toISOString(),
    assignments: sanitizeAssignments(mergeObjectMaps(base.assignments, overlay.assignments)),
    reviewResults: sanitizeReviewResults(mergeObjectMaps(base.reviewResults, overlay.reviewResults)),
    evidenceImages: sanitizeEvidenceImages(mergeObjectMaps(base.evidenceImages, overlay.evidenceImages)),
    reportDrafts: sanitizeReportDrafts(mergeObjectMaps(base.reportDrafts, overlay.reportDrafts)),
    taskQueue: sanitizeTaskQueue(mergeArrayById(base.taskQueue, overlay.taskQueue)),
    activityLog: sanitizeActivityLog(mergeArrayById(base.activityLog, overlay.activityLog)),
  };
}

function jsonResponse(statusCode, body) {
  return {
    statusCode,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Accept",
    },
    body: JSON.stringify(body),
  };
}

exports.handler = async function handler(event) {
  if (event.httpMethod === "OPTIONS") {
    return jsonResponse(200, { ok: true });
  }

  const store = resolveStore();

  if (event.httpMethod === "GET") {
    try {
      const raw = await store.get(STORE_KEY);
      if (!raw) {
        return jsonResponse(200, buildPayload({}));
      }

      const parsed = JSON.parse(raw);
      return jsonResponse(200, buildPayload(parsed));
    } catch (error) {
      console.error("No se pudo leer el estado compartido:", error);
      return jsonResponse(500, { error: "No se pudo leer el estado compartido." });
    }
  }

  if (event.httpMethod === "POST") {
    try {
      const parsedBody = event.body ? JSON.parse(event.body) : {};
      let existingPayload = {};

      try {
        const raw = await store.get(STORE_KEY);
        existingPayload = raw ? JSON.parse(raw) : {};
      } catch (readError) {
        console.warn("No se pudo leer el estado previo para fusionar:", readError);
      }

      const payload = mergePayloads(existingPayload, parsedBody);
      await store.set(STORE_KEY, JSON.stringify(payload));
      return jsonResponse(200, payload);
    } catch (error) {
      console.error("No se pudo guardar el estado compartido:", error);
      return jsonResponse(500, { error: "No se pudo guardar el estado compartido." });
    }
  }

  return jsonResponse(405, { error: "Metodo no permitido." });
};
