import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { APP_ROUTE_MARKER } from "./src/router/routeConfig";

function routeMarkerPlugin(): Plugin {
  let isBuild = false;

  const productionBootstrapStart = "<!-- SANDALA_PRODUCTION_BOOTSTRAP_START -->";
  const productionBootstrapEnd = "<!-- SANDALA_PRODUCTION_BOOTSTRAP_END -->";
  const devConfigStart = "<!-- SANDALA_DEV_BOOTSTRAP_START -->";
  const devConfigEnd = "<!-- SANDALA_DEV_BOOTSTRAP_END -->";
  const devEntryStart = "<!-- SANDALA_DEV_ENTRY_START -->";
  const devEntryEnd = "<!-- SANDALA_DEV_ENTRY_END -->";

  function removeMarkedBlock(html: string, startMarker: string, endMarker: string) {
    const start = html.indexOf(startMarker);
    const end = html.indexOf(endMarker);
    if (start === -1 || end === -1 || end < start) {
      throw new Error(`Sandala HTML markers are missing from index.html: ${startMarker}`);
    }

    return html.slice(0, start) + html.slice(end + endMarker.length);
  }

  function removeMarkerComments(html: string, startMarker: string, endMarker: string) {
    return html.split(startMarker).join("").split(endMarker).join("");
  }

  return {
    name: "sandala-route-marker",
    configResolved(config) {
      isBuild = config.command === "build";
    },
    transformIndexHtml: {
      order: "pre",
      handler(html) {
        let transformedHtml = html
          .split("__SANDALA_APP_ROUTE_MARKER__")
          .join(JSON.stringify(APP_ROUTE_MARKER));

        if (isBuild) {
          transformedHtml = removeMarkedBlock(transformedHtml, devConfigStart, devConfigEnd);
          transformedHtml = removeMarkedBlock(transformedHtml, devEntryStart, devEntryEnd);
          transformedHtml = removeMarkerComments(
            transformedHtml,
            productionBootstrapStart,
            productionBootstrapEnd,
          );
        } else {
          transformedHtml = removeMarkedBlock(
            transformedHtml,
            productionBootstrapStart,
            productionBootstrapEnd,
          );
          transformedHtml = removeMarkerComments(transformedHtml, devConfigStart, devConfigEnd);
          transformedHtml = removeMarkerComments(transformedHtml, devEntryStart, devEntryEnd);
        }

        return transformedHtml;
      },
    },
  };
}

export default defineConfig({
  plugins: [react(), routeMarkerPlugin()],
  base: "./",
  build: {
    outDir: "../sandala/admin_ui_dist",
    emptyOutDir: true,
    assetsDir: "static",
    manifest: "static/manifest.json",
    rollupOptions: {
      input: {
        index: "index.html",
        app: "src/main.tsx",
      },
    },
  },
  server: {
    port: 3001,
    proxy: {
      "^/api/": {
        target: "http://localhost:3000",
      },
      "^/assets/": {
        target: "http://localhost:3000",
      },
    },
  },
});
