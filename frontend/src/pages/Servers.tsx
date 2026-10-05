import { useEffect, useState } from "react";
import * as XLSX from "xlsx";
import { api } from "../lib/api";
import StatusBadge from "../components/StatusBadge";
import type { Connection, Server } from "../lib/types";

type InventoryType = "static" | "dynamic";

type ImportedServer = {
  name: string;
  hostname: string;
  port: number;
  username: string;
  environment: string;
};

export default function Servers() {
  const [servers, setServers] = useState<Server[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);

  // =========================================
  // MAIN PANELS
  // =========================================

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [inventoryType, setInventoryType] =
    useState<InventoryType | null>(null);

  // =========================================
  // MANUAL SERVER FORM
  // =========================================

  const [form, setForm] = useState({
    name: "",
    hostname: "",
    port: 22,
    username: "root",
    environment: "production",
    connection_id: "",
  });

  // =========================================
  // SERVER ACTION STATE
  // =========================================

  const [busyId, setBusyId] = useState<string | null>(null);

  // =========================================
  // INVENTORY IMPORT STATE
  // =========================================

  const [importFile, setImportFile] = useState<File | null>(null);

  const [importedServers, setImportedServers] = useState<
    ImportedServer[]
  >([]);

  const [importError, setImportError] = useState("");

  const [importLoading, setImportLoading] = useState(false);

  // Separate connection for inventory import
  const [inventoryConnectionId, setInventoryConnectionId] =
    useState("");

  // =========================================
  // LOAD SERVERS + CONNECTIONS
  // =========================================

  async function load() {
    try {
      const [serverData, connectionData] = await Promise.all([
        api.get<Server[]>("/servers"),
        api.get<Connection[]>("/connections"),
      ]);

      setServers(serverData);
      setConnections(connectionData);
    } catch (error) {
      console.error("Failed to load servers:", error);
    }
  }

  useEffect(() => {
    load();
  }, []);

  // =========================================
  // MANUAL CREATE SERVER
  // =========================================

  async function createServer(e: React.FormEvent) {
    e.preventDefault();

    try {
      await api.post("/servers", {
        ...form,
        tags: {},
        connection_id: form.connection_id || null,
      });

      alert("Server created successfully.");

      setShowCreateForm(false);

      setForm({
        name: "",
        hostname: "",
        port: 22,
        username: "root",
        environment: "production",
        connection_id: "",
      });

      await load();
    } catch (error) {
      console.error("Failed to create server:", error);
      alert("Failed to create server.");
    }
  }

  // =========================================
  // OPEN INVENTORY
  // =========================================

  function openInventory(type: InventoryType) {
    setShowCreateForm(false);

    setInventoryType(type);

    setImportFile(null);
    setImportedServers([]);
    setImportError("");

    // Reset inventory connection
    setInventoryConnectionId("");

    // Reset file input
    const input = document.getElementById(
      "inventory-file"
    ) as HTMLInputElement | null;

    if (input) {
      input.value = "";
    }
  }

  // =========================================
  // CLOSE INVENTORY
  // =========================================

  function closeInventory() {
    setInventoryType(null);

    setImportFile(null);
    setImportedServers([]);
    setImportError("");

    setImportLoading(false);

    setInventoryConnectionId("");

    const input = document.getElementById(
      "inventory-file"
    ) as HTMLInputElement | null;

    if (input) {
      input.value = "";
    }
  }

  // =========================================
  // READ CSV / XLS / XLSX
  // =========================================

  async function handleInventoryFile(
    e: React.ChangeEvent<HTMLInputElement>
  ) {
    const file = e.target.files?.[0];

    if (!file) {
      return;
    }

    setImportFile(file);
    setImportedServers([]);
    setImportError("");
    setImportLoading(true);

    try {
      const fileName = file.name.toLowerCase();

      const allowedExtensions = [
        ".csv",
        ".xls",
        ".xlsx",
      ];

      const validExtension = allowedExtensions.some(
        (extension) => fileName.endsWith(extension)
      );

      if (!validExtension) {
        setImportError(
          "Please select a CSV, XLS, or XLSX file."
        );
        return;
      }

      // Read file
      const buffer = await file.arrayBuffer();

      // Read Excel/CSV workbook
      const workbook = XLSX.read(buffer, {
        type: "array",
      });

      if (workbook.SheetNames.length === 0) {
        setImportError(
          "The selected file does not contain a worksheet."
        );
        return;
      }

      // First worksheet
      const firstSheet = workbook.SheetNames[0];

      const worksheet = workbook.Sheets[firstSheet];

      // Convert worksheet to JSON
      const rows = XLSX.utils.sheet_to_json<any>(
        worksheet,
        {
          defval: "",
        }
      );

      if (rows.length === 0) {
        setImportError(
          "The selected file is empty."
        );
        return;
      }

      // Parse rows
      const parsedServers: ImportedServer[] =
        rows.map((row) => ({
          name: String(
            row.name ??
              row.Name ??
              row.NAME ??
              ""
          ).trim(),

          hostname: String(
            row.hostname ??
              row.Hostname ??
              row.HOSTNAME ??
              row.ip ??
              row.IP ??
              row["Hostname / IP"] ??
              ""
          ).trim(),

          port:
            Number(
              row.port ??
                row.Port ??
                22
            ) || 22,

          username: String(
            row.username ??
              row.Username ??
              row.USERNAME ??
              "root"
          ).trim(),

          environment: String(
            row.environment ??
              row.Environment ??
              row.ENVIRONMENT ??
              "production"
          ).trim(),
        }));

      // Only keep valid servers
      const validServers = parsedServers.filter(
        (server) =>
          server.name &&
          server.hostname
      );

      const invalidCount =
        parsedServers.length -
        validServers.length;

      if (invalidCount > 0) {
        setImportError(
          `${invalidCount} row(s) were skipped because Name or Hostname/IP was missing.`
        );
      }

      if (validServers.length === 0) {
        setImportError(
          "No valid servers found. Your file must contain name and hostname columns."
        );

        return;
      }

      setImportedServers(validServers);
    } catch (error) {
      console.error(
        "Failed to read inventory file:",
        error
      );

      setImportError(
        "Unable to read the selected file."
      );
    } finally {
      setImportLoading(false);
    }
  }

  // =========================================
  // CREATE IMPORTED SERVERS
  // =========================================

  async function createImportedServers() {
    if (!inventoryType) {
      return;
    }

    // Check connection
    if (!inventoryConnectionId) {
      setImportError(
        "Please select a connection before creating the servers."
      );

      return;
    }

    // Check imported servers
    if (importedServers.length === 0) {
      setImportError(
        "Please select a valid inventory file."
      );

      return;
    }

    setImportLoading(true);
    setImportError("");

    try {
      for (const server of importedServers) {
        await api.post("/servers", {
          name: server.name,
          hostname: server.hostname,
          port: server.port,
          username: server.username,
          environment: server.environment,

          tags: {
            inventory_type: inventoryType,
            imported_from:
              importFile?.name || "",
          },

          // Selected inventory connection
          connection_id:
            inventoryConnectionId,
        });
      }

      alert(
        `${importedServers.length} server(s) created successfully.`
      );

      closeInventory();

      await load();
    } catch (error) {
      console.error(
        "Failed to create imported servers:",
        error
      );

      setImportError(
        "Failed to create servers. Please check the backend logs."
      );
    } finally {
      setImportLoading(false);
    }
  }

  // =========================================
  // TEST SERVER
  // =========================================

  async function test(id: string) {
    setBusyId(id);

    try {
      await api.post(`/servers/${id}/test`);

      alert("Server test completed.");
    } catch (error) {
      console.error(
        "Server test failed:",
        error
      );

      alert("Server test failed.");
    } finally {
      setBusyId(null);
      await load();
    }
  }

  // =========================================
  // DISCOVER SERVER
  // =========================================

  async function discover(id: string) {
    setBusyId(id);

    try {
      await api.post(
        `/servers/${id}/discover`
      );

      alert("Server discovery completed.");
    } catch (error) {
      console.error(
        "Server discovery failed:",
        error
      );

      alert("Server discovery failed.");
    } finally {
      setBusyId(null);
      await load();
    }
  }

  // =========================================
  // DELETE SERVER
  // =========================================

  async function remove(id: string) {
    if (!confirm("Delete this server?")) {
      return;
    }

    try {
      await api.delete(`/servers/${id}`);

      await load();
    } catch (error) {
      console.error(
        "Failed to delete server:",
        error
      );

      alert("Failed to delete server.");
    }
  }

  // =========================================
  // UI
  // =========================================

  return (
    <div className="p-6 space-y-4">

      {/* ===================================== */}
      {/* HEADER */}
      {/* ===================================== */}

      <div className="flex items-center justify-between">

        <h1 className="text-lg font-semibold">
          Servers
        </h1>

        <div className="flex gap-2">

          {/* CREATE SERVER BUTTON */}

          <button
            type="button"
            className="btn-primary"
            onClick={() => {
              setShowCreateForm(
                (value) => !value
              );

              setInventoryType(null);
            }}
          >
            + Create Server
          </button>

          {/* STATIC INVENTORY */}

          <button
            type="button"
            className="btn-secondary"
            onClick={() =>
              openInventory("static")
            }
          >
            Static Inventory
          </button>

          {/* DYNAMIC INVENTORY */}

          <button
            type="button"
            className="btn-secondary"
            onClick={() =>
              openInventory("dynamic")
            }
          >
            Dynamic Inventory
          </button>

        </div>
      </div>

      {/* ===================================== */}
      {/* MANUAL CREATE SERVER FORM */}
      {/* ===================================== */}

      {showCreateForm && (
        <form
          onSubmit={createServer}
          className="card p-4 grid grid-cols-2 gap-3"
        >

          <div className="col-span-2">

            <h2 className="font-medium">
              Create Server
            </h2>

            <p className="text-xs text-neutral-500 mt-1">
              Add a server manually.
            </p>

          </div>

          {/* NAME */}

          <input
            className="input"
            placeholder="Name (e.g. web-01)"
            value={form.name}
            onChange={(e) =>
              setForm({
                ...form,
                name: e.target.value,
              })
            }
            required
          />

          {/* HOSTNAME */}

          <input
            className="input"
            placeholder="Hostname / IP"
            value={form.hostname}
            onChange={(e) =>
              setForm({
                ...form,
                hostname: e.target.value,
              })
            }
            required
          />

          {/* PORT */}

          <input
            className="input"
            placeholder="Port"
            type="number"
            min="1"
            max="65535"
            value={form.port}
            onChange={(e) =>
              setForm({
                ...form,
                port: Number(
                  e.target.value
                ),
              })
            }
          />

          {/* USERNAME */}

          <input
            className="input"
            placeholder="Username"
            value={form.username}
            onChange={(e) =>
              setForm({
                ...form,
                username: e.target.value,
              })
            }
          />

          {/* ENVIRONMENT */}

          <select
            className="input"
            value={form.environment}
            onChange={(e) =>
              setForm({
                ...form,
                environment: e.target.value,
              })
            }
          >
            <option value="production">
              production
            </option>

            <option value="staging">
              staging
            </option>

            <option value="development">
              development
            </option>
          </select>

          {/* CONNECTION */}

          <select
            className="input"
            value={form.connection_id}
            onChange={(e) =>
              setForm({
                ...form,
                connection_id:
                  e.target.value,
              })
            }
          >

            <option value="">
              Select Connection
            </option>

            {connections.map(
              (connection) => (
                <option
                  key={connection.id}
                  value={connection.id}
                >
                  {connection.name}
                  {connection.type
                    ? ` (${connection.type})`
                    : ""}
                </option>
              )
            )}

          </select>

          {/* FORM BUTTONS */}

          <div className="col-span-2 flex gap-2">

            <button
              className="btn-primary"
              type="submit"
            >
              Create
            </button>

            <button
              className="btn-secondary"
              type="button"
              onClick={() =>
                setShowCreateForm(false)
              }
            >
              Cancel
            </button>

          </div>

        </form>
      )}

      {/* ===================================== */}
      {/* STATIC / DYNAMIC INVENTORY */}
      {/* ===================================== */}

      {inventoryType && (
        <div className="card p-5 space-y-4">

          {/* INVENTORY HEADER */}

          <div className="flex items-center justify-between">

            <div>

              <h2 className="text-base font-semibold">

                {inventoryType === "static"
                  ? "Static Inventory"
                  : "Dynamic Inventory"}

              </h2>

              <p className="text-xs text-neutral-500 mt-1">
                Import servers using CSV,
                XLS, or XLSX files.
              </p>

            </div>

            <button
              type="button"
              className="btn-secondary"
              onClick={closeInventory}
              disabled={importLoading}
            >
              Close
            </button>

          </div>

          {/* ================================= */}
          {/* CONNECTION SELECTION */}
          {/* ================================= */}

          <div>

            <label
              htmlFor="inventory-connection"
              className="block text-sm font-medium mb-2"
            >
              Connection
            </label>

            <select
              id="inventory-connection"
              className="input w-full"
              value={inventoryConnectionId}
              onChange={(e) =>
                setInventoryConnectionId(
                  e.target.value
                )
              }
              disabled={importLoading}
            >

              <option value="">
                Select Connection
              </option>

              {connections.map(
                (connection) => (
                  <option
                    key={connection.id}
                    value={connection.id}
                  >
                    {connection.name}
                    {connection.type
                      ? ` (${connection.type})`
                      : ""}
                  </option>
                )
              )}

            </select>

            {connections.length === 0 && (
              <p className="text-xs text-red-500 mt-2">
                No connections available.
                Please create a connection
                first.
              </p>
            )}

            {inventoryConnectionId && (
              <p className="text-xs text-neutral-500 mt-2">
                The selected connection will
                be used for all imported
                servers.
              </p>
            )}

          </div>

          {/* ================================= */}
          {/* FILE UPLOAD */}
          {/* ================================= */}

          <div className="border border-line rounded-lg p-4 bg-neutral-50">

            <label
              htmlFor="inventory-file"
              className="block text-sm font-medium mb-2"
            >
              Select Inventory File
            </label>

            <input
              id="inventory-file"
              type="file"
              accept=".csv,.xls,.xlsx"
              onChange={
                handleInventoryFile
              }
              className="block w-full text-sm"
              disabled={importLoading}
            />

            <p className="text-xs text-neutral-500 mt-2">
              Supported formats: CSV, XLS,
              XLSX
            </p>

            {importFile && (
              <p className="text-xs mt-3">

                Selected:

                <span className="font-medium ml-1">
                  {importFile.name}
                </span>

              </p>
            )}

          </div>

          {/* ================================= */}
          {/* LOADING */}
          {/* ================================= */}

          {importLoading && (
            <div className="text-sm text-neutral-500">
              {importedServers.length > 0
                ? "Creating servers..."
                : "Reading inventory file..."}
            </div>
          )}

          {/* ================================= */}
          {/* ERROR */}
          {/* ================================= */}

          {importError && (
            <div className="rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-600">
              {importError}
            </div>
          )}

          {/* ================================= */}
          {/* PREVIEW */}
          {/* ================================= */}

          {importedServers.length > 0 && (
            <div className="space-y-3">

              <div className="flex items-center justify-between">

                <div>

                  <h3 className="text-sm font-medium">
                    Import Preview
                  </h3>

                  <p className="text-xs text-neutral-500">
                    {importedServers.length}{" "}
                    server
                    {importedServers.length !==
                    1
                      ? "s"
                      : ""}{" "}
                    found
                  </p>

                </div>

              </div>

              {/* PREVIEW TABLE */}

              <div className="border border-line rounded-lg overflow-hidden">

                <div className="overflow-x-auto">

                  <table className="w-full text-sm">

                    <thead className="bg-neutral-50 text-xs text-neutral-500">

                      <tr>

                        <th className="text-left px-4 py-2">
                          Name
                        </th>

                        <th className="text-left px-4 py-2">
                          Hostname / IP
                        </th>

                        <th className="text-left px-4 py-2">
                          Port
                        </th>

                        <th className="text-left px-4 py-2">
                          Username
                        </th>

                        <th className="text-left px-4 py-2">
                          Environment
                        </th>

                      </tr>

                    </thead>

                    <tbody>

                      {importedServers.map(
                        (
                          server,
                          index
                        ) => (
                          <tr
                            key={`${server.hostname}-${index}`}
                            className="border-t border-line"
                          >

                            <td className="px-4 py-2">
                              {server.name}
                            </td>

                            <td className="px-4 py-2">
                              {server.hostname}
                            </td>

                            <td className="px-4 py-2">
                              {server.port}
                            </td>

                            <td className="px-4 py-2">
                              {server.username}
                            </td>

                            <td className="px-4 py-2">
                              {server.environment}
                            </td>

                          </tr>
                        )
                      )}

                    </tbody>

                  </table>

                </div>

              </div>

              {/* ================================= */}
              {/* CREATE + CANCEL BUTTONS */}
              {/* ================================= */}

              <div className="flex justify-end gap-2 pt-2">

                <button
                  type="button"
                  className="btn-secondary"
                  onClick={closeInventory}
                  disabled={importLoading}
                >
                  Cancel
                </button>

                <button
                  type="button"
                  className="btn-primary"
                  onClick={
                    createImportedServers
                  }
                  disabled={
                    importLoading ||
                    importedServers.length ===
                      0 ||
                    !inventoryConnectionId
                  }
                >
                  {importLoading
                    ? "Creating..."
                    : "Create"}
                </button>

              </div>

            </div>
          )}

        </div>
      )}

      {/* ===================================== */}
      {/* EXISTING SERVERS */}
      {/* ===================================== */}

      <div className="card overflow-hidden">

        <div className="px-4 py-3 border-b border-line">

          <h2 className="text-sm font-semibold">
            Existing Servers
          </h2>

          <p className="text-xs text-neutral-500 mt-1">
            Manage your configured
            infrastructure servers.
          </p>

        </div>

        <div className="overflow-x-auto">

          <table className="w-full text-sm">

            <thead className="bg-neutral-50 text-neutral-500 text-xs uppercase">

              <tr>

                <th className="text-left px-4 py-2">
                  Name
                </th>

                <th className="text-left px-4 py-2">
                  Status
                </th>

                <th className="text-left px-4 py-2">
                  OS
                </th>

                <th className="text-left px-4 py-2">
                  Environment
                </th>

                <th className="text-left px-4 py-2">
                  CPU/RAM/Disk
                </th>

                <th className="text-left px-4 py-2">
                  Last Seen
                </th>

                <th className="text-left px-4 py-2">
                  Actions
                </th>

              </tr>

            </thead>

            <tbody>

              {servers.map((server) => (

                <tr
                  key={server.id}
                  className="border-t border-line"
                >

                  {/* NAME */}

                  <td className="px-4 py-2 font-medium">

                    {server.name}

                    <div className="text-xs text-neutral-500">
                      {server.hostname}
                    </div>

                  </td>

                  {/* STATUS */}

                  <td className="px-4 py-2">

                    <StatusBadge
                      status={server.status}
                    />

                  </td>

                  {/* OS */}

                  <td className="px-4 py-2">

                    {server.os_distribution
                      ? `${server.os_distribution} ${server.os_version}`
                      : "—"}

                  </td>

                  {/* ENVIRONMENT */}

                  <td className="px-4 py-2">
                    {server.environment}
                  </td>

                  {/* CPU / RAM / DISK */}

                  <td className="px-4 py-2 text-xs text-neutral-500">

                    {server.cpu_cores ??
                      "—"}{" "}
                    cores /

                    {server.ram_mb
                      ? ` ${Math.round(
                          server.ram_mb /
                            1024
                        )}GB`
                      : " —"}{" "}

                    /

                    {server.disk_gb
                      ? ` ${server.disk_gb}GB`
                      : " —"}

                  </td>

                  {/* LAST SEEN */}

                  <td className="px-4 py-2 text-xs text-neutral-500">

                    {server.last_seen
                      ? new Date(
                          server.last_seen
                        ).toLocaleString()
                      : "Never"}

                  </td>

                  {/* ACTIONS */}

                  <td className="px-4 py-2 space-x-2 whitespace-nowrap">

                    {/* TEST */}

                    <button
                      type="button"
                      className="btn-secondary text-xs"
                      disabled={
                        busyId ===
                        server.id
                      }
                      onClick={() =>
                        test(server.id)
                      }
                    >
                      {busyId ===
                      server.id
                        ? "Working..."
                        : "Test"}
                    </button>

                    {/* DISCOVER */}

                    <button
                      type="button"
                      className="btn-secondary text-xs"
                      disabled={
                        busyId ===
                        server.id
                      }
                      onClick={() =>
                        discover(
                          server.id
                        )
                      }
                    >
                      {busyId ===
                      server.id
                        ? "Working..."
                        : "Discover"}
                    </button>

                    {/* DELETE */}

                    <button
                      type="button"
                      className="btn-danger text-xs"
                      onClick={() =>
                        remove(
                          server.id
                        )
                      }
                    >
                      Delete
                    </button>

                  </td>

                </tr>

              ))}

              {/* EMPTY STATE */}

              {servers.length === 0 && (
                <tr>

                  <td
                    colSpan={7}
                    className="px-4 py-8 text-center text-neutral-400 text-sm"
                  >
                    No servers yet. Add one
                    to get started.
                  </td>

                </tr>
              )}

            </tbody>

          </table>

        </div>

      </div>

    </div>
  );
}