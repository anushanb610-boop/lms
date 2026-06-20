import { useState, useCallback } from "react";

export function useRefresh() {
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const triggerRefresh = useCallback(() => {
    setRefreshTrigger((prev) => prev + 1);
  }, []);

  return { refreshTrigger, triggerRefresh };
}

// Simple global storage for refresh signals
let refreshCallbacks = [];

export function onRefreshNeeded(callback) {
  refreshCallbacks.push(callback);
  return () => {
    refreshCallbacks = refreshCallbacks.filter((cb) => cb !== callback);
  };
}

export function triggerRefreshForAll() {
  refreshCallbacks.forEach((cb) => cb());
}
