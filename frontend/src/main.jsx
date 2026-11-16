import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { QueryClientProvider } from "@tanstack/react-query";
import * as Tooltip from "@radix-ui/react-tooltip";
import { queryClient } from "./api";
import { AuthProvider } from "./auth";
import { ConfirmProvider } from "./components/ui";
import "./styles.css";
import "./shell.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <Tooltip.Provider>
          <ConfirmProvider>
            <AuthProvider>
              <App />
            </AuthProvider>
          </ConfirmProvider>
        </Tooltip.Provider>
      </QueryClientProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
