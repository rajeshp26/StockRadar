/**
 * A performance utility for creating standardized, toggle-able performance marks and measures.
 * This helps us instrument the application to validate our performance SLOs.
 */

// We only enable performance tracking in development to avoid overhead in production.
const ENABLED = process.env.NODE_ENV !== 'production';

/**
 * Placeholder for a future analytics reporting function.
 * This could send data to a service like Datadog, Sentry, or Vercel Speed Insights.
 * @param name - The name of the metric (e.g., "User Authentication").
 * @param duration - The duration of the measurement in milliseconds.
 */
const reportMetric = (name: string, duration: number) => {
  // In the future, this could be: window.analytics?.track('Performance', { metric: name, duration });
  // For now, we are just logging to the console.
};

export const perf = {
  /**
   * Creates a performance mark in the browser's performance timeline.
   * @param name - A descriptive name for the mark.
   */
  mark: (name: string) => {
    if (ENABLED) {
      performance.mark(name);
    }
  },

  /**
   * Creates a performance measure between two marks, logs it to the console,
   * and reports it to our analytics placeholder.
   * @param name - A descriptive name for the measurement (e.g., "User Authentication").
   * @param start - The name of the starting mark.
   * @param end - The name of the ending mark.
   */
  measure: (name: string, start: string, end: string) => {
    if (ENABLED) {
      try {
        performance.measure(name, start, end);
        const measure = performance.getEntriesByName(name).pop();
        if (measure) {
          console.log(`⏱️ ${name}: ${measure.duration.toFixed(2)}ms`);
          reportMetric(name, measure.duration);
        }
      } catch (error) {
        // This can happen if one of the marks doesn't exist. We'll log a warning.
        console.warn(`[Performance] Could not measure "${name}". One of the marks ("${start}" or "${end}") might be missing.`);
      }
    }
  },

  /**
   * Clears all marks and measures to prevent memory leaks in long-running sessions.
   */
  clear: () => {
    if (ENABLED) {
      performance.clearMarks();
      performance.clearMeasures();
    }
  },
};
