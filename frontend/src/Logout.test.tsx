import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import App from "./App";

const mockUser = {
  id: "test-user",
  email: "staff@example.com",
  role: "reviewer",
};

function mockApi(
  logoutResponse: "success" | "error" | "pending" | "unauthorized",
) {
  let resolveLogout: (() => void) | undefined;

  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === "/api/v1/me") {
        return {
          ok: true,
          status: 200,
          json: async () => mockUser,
        } as Response;
      }

      if (url === "/api/v1/auth/logout") {
        if (logoutResponse === "pending") {
          await new Promise<void>((resolve) => {
            resolveLogout = resolve;
          });
        }

        const status =
          logoutResponse === "error"
            ? 500
            : logoutResponse === "unauthorized"
              ? 401
              : 204;

        return {
          ok: status >= 200 && status < 300,
          status,
        } as Response;
      }

      return {
        ok: true,
        status: 200,
        json: async () => [],
      } as Response;
    },
  );

  vi.stubGlobal("fetch", fetchMock);

  return {
    fetchMock,
    finishLogout: () => resolveLogout?.(),
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

test("successful logout redirects to login", async () => {
  document.cookie = "operon_csrf=test-csrf-token";
  const { fetchMock } = mockApi("success");
  const user = userEvent.setup();

  window.location.hash = "#/brain";
  render(<App />);

  const logoutButton = await screen.findByRole("button", {
    name: "Log out",
  });

  await user.click(logoutButton);

  await waitFor(() => {
    expect(window.location.hash).toBe("#/login");
  });

  expect(
    await screen.findByRole("heading", { name: "Welcome back" }),
  ).toBeInTheDocument();

  // The backend rejects a POST without the CSRF header (403).
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/auth/logout",
    expect.objectContaining({
      method: "POST",
      credentials: "include",
      headers: { "X-CSRF-Token": "test-csrf-token" },
    }),
  );
});

test("failed logout displays error and keeps user on the page", async () => {
  mockApi("error");
  const user = userEvent.setup();

  window.location.hash = "#/brain";
  render(<App />);

  const logoutButton = await screen.findByRole("button", {
    name: "Log out",
  });

  await user.click(logoutButton);

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Unable to log out. Please try again.",
  );

  expect(window.location.hash).toBe("#/brain");

  expect(screen.getByRole("heading", { name: "Brain" })).toBeInTheDocument();
});

test("logout button prevents repeated requests while pending", async () => {
  const { fetchMock, finishLogout } = mockApi("pending");
  const user = userEvent.setup();

  window.location.hash = "#/brain";
  render(<App />);

  const logoutButton = await screen.findByRole("button", {
    name: "Log out",
  });

  await user.click(logoutButton);

  expect(screen.getByRole("button", { name: "Logging out..." })).toBeDisabled();

  // Clicking a disabled button must not trigger another request.
  await user.click(screen.getByRole("button", { name: "Logging out..." }));

  const logoutCalls = fetchMock.mock.calls.filter(
    ([url]) => String(url) === "/api/v1/auth/logout",
  );

  expect(logoutCalls).toHaveLength(1);

  finishLogout();

  await waitFor(() => {
    expect(window.location.hash).toBe("#/login");
  });
});

test("expired session during logout redirects to login", async () => {
  const { fetchMock } = mockApi("unauthorized");
  const user = userEvent.setup();

  window.location.hash = "#/brain";
  render(<App />);

  const logoutButton = await screen.findByRole("button", {
    name: "Log out",
  });

  await user.click(logoutButton);

  await waitFor(() => {
    expect(window.location.hash).toBe("#/login");
  });

  expect(
    await screen.findByRole("heading", { name: "Welcome back" }),
  ).toBeInTheDocument();

  expect(screen.queryByRole("alert")).not.toBeInTheDocument();

  const logoutCalls = fetchMock.mock.calls.filter(
    ([url]) => String(url) === "/api/v1/auth/logout",
  );

  expect(logoutCalls).toHaveLength(1);
});
