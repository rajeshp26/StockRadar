let unauthorizedHandler: (() => void) | null = null;

/** Allow auth provider to register a sign-out handler for 401/403 */
export const registerUnauthorizedHandler = (fn: () => void) => {
  unauthorizedHandler = fn;
};

export const getUnauthorizedHandler = () => unauthorizedHandler;
