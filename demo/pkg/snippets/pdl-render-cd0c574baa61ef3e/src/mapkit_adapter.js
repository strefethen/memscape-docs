const REGISTRY_KEY = '__pdlMapKitRegistry';
const MAPKIT_SCRIPT_KEY = '__pdlMapKitScriptPromise';
const MAPKIT_INIT_KEY = '__pdlMapKitInitPromise';
const DEFAULT_TOKEN_URL = '/api/mapkit-token';
const MAPKIT_SCRIPT_URL = 'https://cdn.apple-mapkit.com/mk/5.x.x/mapkit.js';
const SESSION_TOKEN_KEY = 'pdl.mapkit.token';

function registry() {
  if (!(window[REGISTRY_KEY] instanceof Map)) {
    window[REGISTRY_KEY] = new Map();
  }
  return window[REGISTRY_KEY];
}

function ensureSurface(element) {
  let surface = element.querySelector('.ab-map-surface');
  if (!surface) {
    surface = document.createElement('div');
    surface.className = 'ab-map-surface';
    element.appendChild(surface);
  }
  syncSurfacePresentation(element, surface);
  return surface;
}

function syncSurfacePresentation(element, surface) {
  if (!surface) {
    return;
  }

  const radius = window.getComputedStyle(element).borderRadius;
  surface.style.overflow = 'hidden';
  surface.style.borderRadius = radius;

  if (radius && radius !== '0px') {
    surface.style.clipPath = `inset(0 round ${radius})`;
  } else {
    surface.style.removeProperty('clip-path');
  }
}

function resolveTokenUrl() {
  const params = new URLSearchParams(window.location.search);
  const queryValue = params.get('mapkitTokenUrl');
  if (queryValue) {
    return new URL(queryValue, window.location.href).toString();
  }

  const globalValue = window.__PDL_MAPKIT_TOKEN_URL__;
  if (typeof globalValue === 'string' && globalValue.trim()) {
    return new URL(globalValue, window.location.href).toString();
  }

  const meta = document.querySelector('meta[name="pdl-mapkit-token-url"]');
  const metaValue = meta?.getAttribute('content');
  if (metaValue && metaValue.trim()) {
    return new URL(metaValue, window.location.href).toString();
  }

  return new URL(DEFAULT_TOKEN_URL, window.location.href).toString();
}

function resolveInlineToken() {
  const params = new URLSearchParams(window.location.search);
  const queryToken = params.get('mapkitToken');
  if (typeof queryToken === 'string' && queryToken.trim()) {
    return queryToken.trim();
  }

  const sessionToken = window.sessionStorage?.getItem(SESSION_TOKEN_KEY);
  if (typeof sessionToken === 'string' && sessionToken.trim()) {
    return sessionToken.trim();
  }

  const globalToken = window.__PDL_MAPKIT_TOKEN__;
  if (typeof globalToken === 'string' && globalToken.trim()) {
    return globalToken.trim();
  }

  const meta = document.querySelector('meta[name="pdl-mapkit-token"]');
  const metaToken = meta?.getAttribute('content');
  if (metaToken && metaToken.trim()) {
    return metaToken.trim();
  }

  return null;
}

function normalizeTokenCandidate(candidate) {
  if (typeof candidate === 'string' && candidate.trim()) {
    return candidate.trim();
  }

  if (
    candidate &&
    typeof candidate === 'object' &&
    typeof candidate.token === 'string' &&
    candidate.token.trim()
  ) {
    return candidate.token.trim();
  }

  return null;
}

async function resolveTokenFromProvider() {
  const provider = window.__PDL_GET_MAPKIT_TOKEN__;
  if (typeof provider !== 'function') {
    return null;
  }

  const candidate = await provider();
  const token = normalizeTokenCandidate(candidate);
  if (!token) {
    throw new Error('window.__PDL_GET_MAPKIT_TOKEN__ did not return a token string');
  }

  return token;
}

async function ensureMapKitScript() {
  if (window.mapkit) {
    return window.mapkit;
  }

  if (!window[MAPKIT_SCRIPT_KEY]) {
    window[MAPKIT_SCRIPT_KEY] = new Promise((resolve, reject) => {
      const existing = document.querySelector(`script[src="${MAPKIT_SCRIPT_URL}"]`);
      if (existing && window.mapkit) {
        resolve(window.mapkit);
        return;
      }

      const script = existing || document.createElement('script');
      script.src = MAPKIT_SCRIPT_URL;
      script.crossOrigin = 'anonymous';
      script.async = true;
      script.onload = () => resolve(window.mapkit);
      script.onerror = () => reject(new Error(`Failed to load Apple MapKit JS from ${MAPKIT_SCRIPT_URL}`));
      if (!existing) {
        document.head.appendChild(script);
      }
    });
  }

  return window[MAPKIT_SCRIPT_KEY];
}

async function fetchMapKitToken() {
  const providerToken = await resolveTokenFromProvider();
  if (providerToken) {
    return providerToken;
  }

  const inlineToken = resolveInlineToken();
  if (inlineToken) {
    return inlineToken;
  }

  const tokenUrl = resolveTokenUrl();
  let response;
  try {
    response = await fetch(tokenUrl, {
      credentials: 'include',
      headers: { Accept: 'application/json' },
    });
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error(
        `Failed to fetch MapKit token from ${tokenUrl}. ` +
          'Use a same-origin /api/mapkit-token endpoint, allow this preview origin in CORS, ' +
          'or inject window.__PDL_MAPKIT_TOKEN__ / window.__PDL_GET_MAPKIT_TOKEN__.',
      );
    }
    throw error;
  }

  if (!response.ok) {
    const details = await safeResponseText(response);
    throw new Error(`MapKit token request failed (${response.status}) at ${tokenUrl}${details ? `: ${details}` : ''}`);
  }

  const payload = await response.json();
  if (!payload || typeof payload.token !== 'string' || payload.token.length === 0) {
    throw new Error(`MapKit token response from ${tokenUrl} did not include a token`);
  }

  return payload.token;
}

async function safeResponseText(response) {
  try {
    const text = await response.text();
    return text.trim().slice(0, 240);
  } catch (_error) {
    return '';
  }
}

async function ensureMapKitInitialized() {
  if (window.mapkit?._pdlReady) {
    return window.mapkit;
  }

  if (!window[MAPKIT_INIT_KEY]) {
    window[MAPKIT_INIT_KEY] = (async () => {
      const mapkit = await ensureMapKitScript();
      const token = await fetchMapKitToken();
      mapkit.init({
        authorizationCallback(done) {
          done(token);
        },
      });
      mapkit._pdlReady = true;
      return mapkit;
    })().catch((error) => {
      window[MAPKIT_INIT_KEY] = null;
      throw error;
    });
  }

  return window[MAPKIT_INIT_KEY];
}

function isVisible(element) {
  if (!element?.isConnected) {
    return false;
  }

  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function dispatchControlAction(source, controlName, event, params, instanceID) {
  const detail = { controlName, event };
  if (Number.isSafeInteger(instanceID)) {
    detail.instanceID = instanceID;
  }
  if (params && Object.keys(params).length > 0) {
    detail.params = params;
  }
  source.dispatchEvent(new CustomEvent('ab-control-action', {
    bubbles: true,
    detail,
  }));
}

function featureVisibility(show) {
  if (window.mapkit?.FeatureVisibility) {
    return show ? window.mapkit.FeatureVisibility.Visible : window.mapkit.FeatureVisibility.Hidden;
  }
  return !!show;
}

function mapTypeForStyle(style) {
  const types = window.mapkit?.Map?.MapTypes;
  if (!types) {
    return undefined;
  }

  switch (style) {
    case 'hybrid':
      return types.Hybrid;
    case 'satellite':
    case 'imagery':
      return types.Satellite;
    default:
      return types.Standard;
  }
}

function coordinate(lat, lng) {
  return new window.mapkit.Coordinate(Number(lat) || 0, Number(lng) || 0);
}

function regionFromConfig(config) {
  const span = Number.isFinite(Number(config.span)) && Number(config.span) > 0
    ? Number(config.span)
    : 0.05;
  return new window.mapkit.CoordinateRegion(
    coordinate(config.centerLat, config.centerLng),
    new window.mapkit.CoordinateSpan(span, span),
  );
}

function regionSnapshot(region) {
  if (!region?.center || !region?.span) {
    return null;
  }

  return {
    centerLat: Number(region.center.latitude) || 0,
    centerLng: Number(region.center.longitude) || 0,
    span: Number(region.span.latitudeDelta) || 0.05,
  };
}

function regionFromSnapshot(snapshot) {
  if (!snapshot) {
    return null;
  }

  return new window.mapkit.CoordinateRegion(
    coordinate(snapshot.centerLat, snapshot.centerLng),
    new window.mapkit.CoordinateSpan(snapshot.span, snapshot.span),
  );
}

function markerGlyph(icon) {
  switch (icon) {
    case 'building.2.fill':
      return '🏢';
    case 'infinity':
      return '∞';
    case 'star.fill':
      return '★';
    case 'mappin.circle.fill':
      return '📍';
    default:
      return undefined;
  }
}

function ensureErrorOverlay(element) {
  let overlay = element.querySelector('.ab-map-error');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.className = 'ab-map-error';
    element.appendChild(overlay);
  }
  return overlay;
}

function clearError(element) {
  element.removeAttribute('data-ab-map-state');
  const overlay = element.querySelector('.ab-map-error');
  if (overlay) {
    overlay.remove();
  }
}

function showError(element, error) {
  const overlay = ensureErrorOverlay(element);
  overlay.textContent = error instanceof Error ? error.message : String(error);
  element.setAttribute('data-ab-map-state', 'error');
}

function createEntry(element, config) {
  const entry = {
    controlId: config.controlId,
    element,
    config,
    map: null,
    markersById: new Map(),
    pendingMarkers: null,
    busy: false,
    retryCount: 0,
    suppressRegionChange: 0,
    authoredRegionKey: null,
    liveRegionSnapshot: null,
    liveRegionAuthoredKey: null,
    resizeObserver: null,
    initializing: null,
    onRegionStart: null,
    onRegionEnd: null,
    onSelect: null,
  };

  if (typeof ResizeObserver !== 'undefined') {
    entry.resizeObserver = new ResizeObserver(() => {
      sync_mapkit_map(entry.element, entry.config);
    });
    entry.resizeObserver.observe(element);
  }

  return entry;
}

function ensureEntry(element, config) {
  const maps = registry();
  const existing = maps.get(config.controlId);
  const preservedRegionSnapshot = existing?.liveRegionSnapshot ?? null;
  const preservedRegionAuthoredKey = existing?.liveRegionAuthoredKey ?? null;
  if (existing && existing.element !== element) {
    destroyEntry(existing);
  }

  const entry = maps.get(config.controlId) || createEntry(element, config);
  entry.element = element;
  entry.config = config;
  ensureSurface(element);
  if (preservedRegionSnapshot) {
    entry.liveRegionSnapshot = preservedRegionSnapshot;
    entry.liveRegionAuthoredKey = preservedRegionAuthoredKey;
  }
  maps.set(config.controlId, entry);
  return entry;
}

function applyMapBoolean(map, property, value) {
  try {
    if (property in map) {
      map[property] = value;
    }
  } catch (error) {
    console.warn(`[PDL MapKit] Failed to apply ${property}:`, error);
  }
}

function applyRegion(entry, region) {
  if (!entry.map) {
    return;
  }

  if (typeof entry.map.setRegionAnimated === 'function') {
    entry.map.setRegionAnimated(region, false);
    return;
  }

  if (typeof entry.map.setRegion === 'function') {
    entry.map.setRegion(region);
    return;
  }

  if ('region' in entry.map) {
    entry.map.region = region;
    return;
  }

  throw new Error('MapKit map does not expose a writable region API');
}

function buildMarkerAnnotation(marker) {
  const annotation = new window.mapkit.MarkerAnnotation(coordinate(marker.lat, marker.lng), {
    title: marker.label || '',
    color: marker.tint || '#FF3B30',
    glyphText: markerGlyph(marker.icon),
  });

  annotation.data = {
    controlId: marker.controlId,
    instanceID: marker.instanceID,
    lat: Number(marker.lat) || 0,
    lng: Number(marker.lng) || 0,
    label: marker.label || '',
    icon: marker.icon || '',
    tint: marker.tint || '#FF3B30',
    hasTap: !!marker.hasTap,
  };

  return annotation;
}

function sameMarker(annotation, marker) {
  const data = annotation?.data || {};
  return data.lat === (Number(marker.lat) || 0)
    && data.instanceID === marker.instanceID
    && data.lng === (Number(marker.lng) || 0)
    && data.label === (marker.label || '')
    && data.icon === (marker.icon || '')
    && data.tint === (marker.tint || '#FF3B30')
    && data.hasTap === !!marker.hasTap;
}

function diffMarkers(currentById, nextMarkers) {
  const add = [];
  const remove = [];
  const seen = new Set();

  for (const marker of nextMarkers || []) {
    const markerId = marker?.controlId;
    if (!markerId) {
      continue;
    }

    const lat = Number(marker.lat);
    const lng = Number(marker.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      continue;
    }

    seen.add(markerId);
    const existing = currentById.get(markerId);
    if (!existing) {
      add.push(buildMarkerAnnotation(marker));
      continue;
    }

    if (!sameMarker(existing, marker)) {
      remove.push(existing);
      add.push(buildMarkerAnnotation(marker));
    }
  }

  for (const [markerId, annotation] of currentById.entries()) {
    if (!seen.has(markerId)) {
      remove.push(annotation);
    }
  }

  return { add, remove };
}

function applyMarkerDiff(entry, diff) {
  if (diff.remove.length > 0) {
    entry.map.removeAnnotations(diff.remove);
    for (const annotation of diff.remove) {
      const markerId = annotation?.data?.controlId;
      if (markerId) {
        entry.markersById.delete(markerId);
      }
    }
  }

  if (diff.add.length > 0) {
    entry.map.addAnnotations(diff.add);
    for (const annotation of diff.add) {
      const markerId = annotation?.data?.controlId;
      if (markerId) {
        entry.markersById.set(markerId, annotation);
      }
    }
  }
}

function flushMarkerSync(entry) {
  if (!entry.map || !entry.pendingMarkers) {
    return;
  }

  const nextMarkers = entry.pendingMarkers;
  entry.pendingMarkers = null;
  const diff = diffMarkers(entry.markersById, nextMarkers);
  if (diff.add.length === 0 && diff.remove.length === 0) {
    entry.retryCount = 0;
    return;
  }

  try {
    applyMarkerDiff(entry, diff);
    entry.retryCount = 0;
  } catch (error) {
    console.warn('[PDL MapKit] Marker sync failed, retrying:', error);
    if (entry.retryCount < 2) {
      entry.retryCount += 1;
      entry.pendingMarkers = nextMarkers;
      requestAnimationFrame(() => flushMarkerSync(entry));
      return;
    }

    entry.retryCount = 0;
    showError(entry.element, new Error(`Map marker update failed: ${error instanceof Error ? error.message : String(error)}`));
  }
}

function scheduleMarkerSync(entry, markers) {
  entry.pendingMarkers = markers || [];
  if (entry.busy) {
    return;
  }
  requestAnimationFrame(() => flushMarkerSync(entry));
}

function attachListeners(entry) {
  entry.onRegionStart = () => {
    entry.busy = true;
  };

  entry.onRegionEnd = (event) => {
    entry.busy = false;
    flushMarkerSync(entry);

    if (entry.suppressRegionChange > 0) {
      entry.suppressRegionChange -= 1;
      return;
    }

    if (!entry.config.hasChanged) {
      return;
    }

    const region = entry.map?.region || event?.target?.region;
    if (!region?.center || !region?.span) {
      return;
    }

    entry.liveRegionSnapshot = regionSnapshot(region);
    entry.liveRegionAuthoredKey = entry.config.authoredRegionKey;

    dispatchControlAction(entry.element, entry.config.controlId, 'changed', {
      lat: region.center.latitude,
      lng: region.center.longitude,
      span: region.span.latitudeDelta,
    }, entry.config.instanceID);
  };

  entry.onSelect = (event) => {
    const marker = event?.annotation?.data;
    if (!marker) {
      return;
    }

    if (marker.hasTap) {
      dispatchControlAction(entry.element, marker.controlId, 'tap', {
        lat: marker.lat,
        lng: marker.lng,
        label: marker.label,
      }, marker.instanceID);
    }

    // MapKit prohibits selection changes during its select callback. Clear it
    // on the next frame so repeated marker taps remain possible.
    requestAnimationFrame(() => {
      try {
        if (typeof entry.map?.deselectAnnotation === 'function') {
          entry.map.deselectAnnotation(event.annotation);
        } else if (entry.map && 'selectedAnnotation' in entry.map) {
          entry.map.selectedAnnotation = null;
        }
      } catch (_error) {
        // Best effort — repeated taps still work on most builds without explicit deselection.
      }
    });
  };

  entry.map.addEventListener('region-change-start', entry.onRegionStart);
  entry.map.addEventListener('region-change-end', entry.onRegionEnd);
  entry.map.addEventListener('select', entry.onSelect);
}

function applyConfig(entry) {
  if (!entry.map) {
    return;
  }

  clearError(entry.element);

  try {
    const mapType = mapTypeForStyle(entry.config.style);
    if (mapType !== undefined && 'mapType' in entry.map) {
      entry.map.mapType = mapType;
    }
  } catch (error) {
    console.warn('[PDL MapKit] Failed to apply map style:', error);
  }

  applyMapBoolean(entry.map, 'showsCompass', featureVisibility(!!entry.config.showsCompass));
  applyMapBoolean(entry.map, 'showsScale', featureVisibility(!!entry.config.showsScale));
  applyMapBoolean(entry.map, 'showsUserLocation', !!entry.config.showsUserLocation);
  applyMapBoolean(entry.map, 'showsUserLocationControl', featureVisibility(!!entry.config.showsUserLocationButton));
  applyMapBoolean(entry.map, 'showsUserLocationButton', featureVisibility(!!entry.config.showsUserLocationButton));
  applyMapBoolean(entry.map, 'showsPitchControl', featureVisibility(!!entry.config.showsPitchToggle));
  applyMapBoolean(entry.map, 'showsPitchToggle', featureVisibility(!!entry.config.showsPitchToggle));

  const interactionsEnabled = entry.config.enabled !== false;
  applyMapBoolean(entry.map, 'isScrollEnabled', interactionsEnabled && entry.config.allowsScroll !== false);
  applyMapBoolean(entry.map, 'isZoomEnabled', interactionsEnabled && entry.config.allowsZoom !== false);
  applyMapBoolean(entry.map, 'isRotationEnabled', interactionsEnabled && entry.config.allowsRotate !== false);
  applyMapBoolean(entry.map, 'isPitchEnabled', interactionsEnabled && entry.config.allowsPitch !== false);

  if (entry.authoredRegionKey !== entry.config.authoredRegionKey) {
    const preservedRegion = entry.liveRegionAuthoredKey === entry.config.authoredRegionKey
      ? regionFromSnapshot(entry.liveRegionSnapshot)
      : null;
    entry.authoredRegionKey = entry.config.authoredRegionKey;
    entry.suppressRegionChange += 1;
    applyRegion(entry, preservedRegion || regionFromConfig(entry.config));
  }

  scheduleMarkerSync(entry, Array.isArray(entry.config.markers) ? entry.config.markers : []);
}

async function ensureMap(entry) {
  if (entry.map) {
    applyConfig(entry);
    return;
  }

  if (!isVisible(entry.element)) {
    return;
  }

  if (!entry.initializing) {
    entry.initializing = (async () => {
      clearError(entry.element);
      await ensureMapKitInitialized();

      if (!entry.element.isConnected || !isVisible(entry.element)) {
        return;
      }

      if (!entry.map) {
        entry.map = new window.mapkit.Map(ensureSurface(entry.element), {
          center: coordinate(entry.config.centerLat, entry.config.centerLng),
          mapType: mapTypeForStyle(entry.config.style),
          showsCompass: featureVisibility(!!entry.config.showsCompass),
          showsScale: featureVisibility(!!entry.config.showsScale),
        });
        attachListeners(entry);
      }

      applyConfig(entry);
    })().catch((error) => {
      console.error('[PDL MapKit] Failed to initialize map:', error);
      showError(entry.element, error);
    }).finally(() => {
      entry.initializing = null;
    });
  }

  await entry.initializing;
}

function destroyEntry(entry) {
  try {
    entry.resizeObserver?.disconnect();
  } catch (_error) {
    // ignore observer cleanup failures
  }

  if (entry.map) {
    try {
      if (entry.onRegionStart) {
        entry.map.removeEventListener('region-change-start', entry.onRegionStart);
      }
      if (entry.onRegionEnd) {
        entry.map.removeEventListener('region-change-end', entry.onRegionEnd);
      }
      if (entry.onSelect) {
        entry.map.removeEventListener('select', entry.onSelect);
      }
      if (entry.markersById.size > 0) {
        entry.map.removeAnnotations(Array.from(entry.markersById.values()));
      }
      if (typeof entry.map.destroy === 'function') {
        entry.map.destroy();
      }
    } catch (error) {
      console.warn('[PDL MapKit] Failed to destroy map cleanly:', error);
    }
  }

  registry().delete(entry.controlId);
}

export function sync_mapkit_map(element, config) {
  const entry = ensureEntry(element, config);
  ensureMap(entry).catch((error) => {
    console.error('[PDL MapKit] sync failed:', error);
    showError(element, error);
  });
}

export function prune_inactive_mapkit_maps(activeIds) {
  const active = new Set(Array.isArray(activeIds) ? activeIds : []);
  for (const [controlId, entry] of registry().entries()) {
    if (!active.has(controlId) || !entry.element?.isConnected) {
      destroyEntry(entry);
    }
  }
}
