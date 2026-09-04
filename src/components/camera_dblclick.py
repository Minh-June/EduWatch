"""Event-only bridge for double-clicking a monitoring camera frame."""

from collections.abc import Callable

import streamlit as st


_CAMERA_DBLCLICK_JS = r"""
export default function(component) {
  const { data, setTriggerValue } = component;
  const cameraId = Number(data?.camera_id);
  const registryKey = `eduwatch-monitor-camera-dblclick-${cameraId}`;
  const registry = globalThis.__eduwatchCameraDblclickRegistry ??= new Map();
  const previousCleanup = registry.get(registryKey);

  if (typeof previousCleanup === "function") {
    previousCleanup();
  }
  registry.delete(registryKey);

  const viewMode = data?.view_mode;

  if (!Number.isInteger(cameraId) || !["grid", "focus"].includes(viewMode)) {
    return;
  }

  let lastDispatchAt = Number.NEGATIVE_INFINITY;

  const handleDoubleClick = (event) => {
    const frame = event.target instanceof Element
      ? event.target.closest(
          ".ewmon-card > .ewmon-dblclick-frame[data-ewmon-camera-id]"
        )
      : null;
    const targetCameraId = frame?.getAttribute("data-ewmon-camera-id");

    if (
      !frame ||
      !document.querySelector(".ewmon-page") ||
      Number(targetCameraId) !== cameraId ||
      event.button !== 0 ||
      event.defaultPrevented
    ) {
      return;
    }

    const now = performance.now();
    if (now - lastDispatchAt < 250) {
      return;
    }
    lastDispatchAt = now;

    event.preventDefault();
    event.stopPropagation();
    setTriggerValue("dblclick", Number(targetCameraId));
  };

  document.addEventListener("dblclick", handleDoubleClick);

  const cleanup = () => {
    document.removeEventListener("dblclick", handleDoubleClick);
  };
  registry.set(registryKey, cleanup);

  return () => {
    if (registry.get(registryKey) === cleanup) {
      cleanup();
      registry.delete(registryKey);
    }
  };
}
"""


def create_camera_dblclick_bridge() -> Callable[..., None]:
    """Register the component for this script run and return its mount helper."""
    component = st.components.v2.component(
        "eduwatch_monitor_camera_dblclick",
        js=_CAMERA_DBLCLICK_JS,
    )

    def camera_dblclick_bridge(
        camera_id: int,
        view_mode: str,
        *,
        key: str,
        on_double_click: Callable[[], None],
    ) -> None:
        """Mount an invisible listener for one rendered camera frame."""
        component(
            key=key,
            data={
                "camera_id": int(camera_id),
                "view_mode": str(view_mode),
            },
            width="content",
            height="content",
            on_dblclick_change=on_double_click,
        )

    return camera_dblclick_bridge
