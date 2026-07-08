const { getStore } = require("@netlify/blobs");

const STORE_NAME = "tramites-iprus";
const STORE_KEY = "shared-state";
const DEFAULT_TITLE = "TRAMITES IPRUS SHARED STATE";

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

function buildPayload(rawPayload) {
  const payload = rawPayload && typeof rawPayload === "object" ? rawPayload : {};
  return {
    title: typeof payload.title === "string" && payload.title.trim() ? payload.title.trim() : DEFAULT_TITLE,
    sourceDate: typeof payload.sourceDate === "string" ? payload.sourceDate : "",
    generatedAt: new Date().toISOString(),
    assignments: sanitizeAssignments(payload.assignments),
    reviewResults: sanitizeReviewResults(payload.reviewResults),
    evidenceImages: sanitizeEvidenceImages(payload.evidenceImages),
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

  const store = getStore(STORE_NAME);

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
      const payload = buildPayload(parsedBody);
      await store.set(STORE_KEY, JSON.stringify(payload));
      return jsonResponse(200, payload);
    } catch (error) {
      console.error("No se pudo guardar el estado compartido:", error);
      return jsonResponse(500, { error: "No se pudo guardar el estado compartido." });
    }
  }

  return jsonResponse(405, { error: "Metodo no permitido." });
};
