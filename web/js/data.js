import { DATA } from './config.js';

async function getJSON(url) {
  const res = await fetch(url, { cache: 'no-cache' });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`);
  return res.json();
}

export async function loadAll(onProgress = () => {}) {
  onProgress('Fetching project data…');
  const [projects, corridors, meta] = await Promise.all([
    getJSON(DATA.projects), getJSON(DATA.corridors), getJSON(DATA.meta),
  ]);

  onProgress('Fetching detail records…');
  // details.json is the big one; fetched up front because the whole dataset is
  // small today. Past a few thousand projects this becomes a per-click fetch.
  const [details, changes] = await Promise.all([
    getJSON(DATA.details).catch(() => ({})),
    getJSON(DATA.changes).catch(() => []),
  ]);

  const rows = projects.features.map((f) => ({
    ...f.properties,
    lng: f.geometry.coordinates[0],
    lat: f.geometry.coordinates[1],
  }));

  const arcs = corridors.features.map((f) => {
    const c = f.geometry.coordinates;
    return {
      id: f.properties.id,
      title: f.properties.title,
      status: f.properties.status,
      is_blocked: f.properties.is_blocked,
      startLng: c[0][0], startLat: c[0][1],
      endLng: c[c.length - 1][0], endLat: c[c.length - 1][1],
    };
  });

  return { rows, arcs, details, changes, meta };
}
