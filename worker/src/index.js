/**
 * TIFLO — Stremio addon.
 *
 * Един манифест за всички филми. Stremio пита за конкретен IMDB id,
 * Worker-ът гледа в KV какво знаем за него и връща поток, ако има
 * готово аудио.
 *
 * Маршрути:
 *   /manifest.json
 *   /stream/movie/tt0133093.json
 *   /audio/tt0133093/bg.mp3      -> отдава от R2
 *   /admin/status?id=tt...       -> служебно, иска ADMIN_TOKEN
 *
 * Състоянията в KV са три: ready, pending, failed. Всичко останало
 * се смята за "не сме го виждали".
 */

const MANIFEST = {
  id: "lab.emillion.tiflo",
  version: "0.2.0",
  name: "TIFLO — аудио дескрипция",
  description:
    "Озвучаване на субтитри за хора с увредено зрение. Добавя отделен " +
    "аудио поток с прочетени реплики, всеки герой с различен глас.",
  resources: ["stream"],
  types: ["movie"],
  idPrefixes: ["tt"],
  catalogs: [],
  behaviorHints: { configurable: false, configurationRequired: false },
};

const LANGS = { bg: "Български", en: "English" };

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

const json = (data, status = 200, maxAge = 60) =>
  new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": `public, max-age=${maxAge}`,
      ...CORS,
    },
  });

/** Пази ни от боклук в KV ключовете и в R2 пътищата. */
const validId = (id) => /^tt\d{7,10}$/.test(id);

async function readState(env, id) {
  const raw = await env.STATE.get(`movie:${id}`);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/**
 * Заявка за филм, който още не сме виждали. Записва се, но само
 * веднъж — повторните отваряния не пренареждат опашката.
 */
async function enqueue(env, id) {
  const key = `movie:${id}`;
  if (await env.STATE.get(key)) return;
  await env.STATE.put(
    key,
    JSON.stringify({ status: "pending", since: Date.now(), langs: [] }),
    { expirationTtl: 60 * 60 * 24 * 7 },
  );
  await env.STATE.put(`queue:${Date.now()}:${id}`, id, {
    expirationTtl: 60 * 60 * 24 * 7,
  });
}

function streamsFor(id, state, origin) {
  if (!state || state.status !== "ready") return [];
  return (state.langs || []).map((lang) => ({
    name: "TIFLO",
    title: `Аудио дескрипция — ${LANGS[lang] || lang}`,
    url: `${origin}/audio/${id}/${lang}.mp3`,
    behaviorHints: { notWebReady: false },
  }));
}

async function handleStream(env, id, origin) {
  if (!validId(id)) return json({ streams: [] }, 200, 3600);

  const state = await readState(env, id);

  if (state?.status === "ready") {
    return json({ streams: streamsFor(id, state, origin) }, 200, 3600);
  }

  if (!state) await enqueue(env, id);

  // Плейърът не бива да получава "поток", който не свири. По-честно е
  // празен списък — Stremio просто не показва нищо от нас.
  return json({ streams: [] }, 200, 60);
}

async function handleAudio(env, id, lang) {
  if (!validId(id) || !/^[a-z]{2}$/.test(lang)) {
    return new Response("bad request", { status: 400, headers: CORS });
  }
  const object = await env.AUDIO.get(`${id}/${lang}.mp3`);
  if (!object) return new Response("not found", { status: 404, headers: CORS });

  const headers = new Headers(CORS);
  object.writeHttpMetadata(headers);
  headers.set("Content-Type", "audio/mpeg");
  headers.set("Cache-Control", "public, max-age=604800");
  headers.set("Accept-Ranges", "bytes");
  headers.set("etag", object.httpEtag);
  return new Response(object.body, { headers });
}

/** Опашката се чете и отбелязва оттук — от машината, която синтезира. */
async function handleAdmin(request, env, url) {
  const token = (request.headers.get("Authorization") || "").replace(
    /^Bearer\s+/i,
    "",
  );
  if (!env.ADMIN_TOKEN || token !== env.ADMIN_TOKEN) {
    return new Response("unauthorized", { status: 401, headers: CORS });
  }

  if (url.pathname === "/admin/queue") {
    const list = await env.STATE.list({ prefix: "queue:", limit: 50 });
    return json({ pending: list.keys.map((k) => k.name.split(":").pop()) });
  }

  if (url.pathname === "/admin/status" && request.method === "POST") {
    const body = await request.json().catch(() => null);
    if (!body?.id || !validId(body.id)) return json({ error: "bad id" }, 400);
    await env.STATE.put(
      `movie:${body.id}`,
      JSON.stringify({
        status: body.status || "ready",
        langs: body.langs || ["bg"],
        updated: Date.now(),
      }),
    );
    return json({ ok: true, id: body.id });
  }

  return new Response("not found", { status: 404, headers: CORS });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = url.origin;

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }

    if (url.pathname === "/" || url.pathname === "/manifest.json") {
      return json(MANIFEST, 200, 3600);
    }

    const stream = url.pathname.match(/^\/stream\/movie\/(tt[\w]+)\.json$/);
    if (stream) return handleStream(env, stream[1], origin);

    const audio = url.pathname.match(/^\/audio\/(tt[\w]+)\/([a-z]{2})\.mp3$/);
    if (audio) return handleAudio(env, audio[1], audio[2]);

    if (url.pathname.startsWith("/admin/")) {
      return handleAdmin(request, env, url);
    }

    return new Response("not found", { status: 404, headers: CORS });
  },
};
