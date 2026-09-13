import * as vscode from "vscode";
import { ServerManager } from "./serverManager";
import { OperationalCapability } from "./types";

type TreeNode = GroupNode | CapabilityNode | MessageNode;
interface GroupNode { type: "group"; label: string; children: CapabilityNode[] }
interface CapabilityNode { type: "capability"; capability: OperationalCapability }
interface MessageNode { type: "message"; label: string }

export class CapabilitiesTree implements vscode.TreeDataProvider<TreeNode> {
  private readonly changed = new vscode.EventEmitter<TreeNode | undefined>();
  readonly onDidChangeTreeData = this.changed.event;
  private roots: TreeNode[] = [{ type: "message", label: "Start the API or refresh capabilities." }];

  constructor(private readonly server: ServerManager) {}

  async refresh(): Promise<void> {
    const { client } = await this.server.ensureStarted();
    const response = await client.capabilities();
    const groups = new Map<string, CapabilityNode[]>();
    for (const capability of response.capabilities.operational_manifest) {
      const entries = groups.get(capability.kind) ?? [];
      entries.push({ type: "capability", capability });
      groups.set(capability.kind, entries);
    }
    this.roots = [...groups.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([label, children]) => ({
        type: "group",
        label,
        children: children.sort((left, right) =>
          left.capability.canonical.localeCompare(right.capability.canonical)),
      }));
    this.changed.fire(undefined);
  }

  getTreeItem(element: TreeNode): vscode.TreeItem {
    if (element.type === "group") {
      const item = new vscode.TreeItem(element.label, vscode.TreeItemCollapsibleState.Collapsed);
      item.description = String(element.children.length);
      return item;
    }
    if (element.type === "message") {
      return new vscode.TreeItem(element.label, vscode.TreeItemCollapsibleState.None);
    }
    const capability = element.capability;
    const item = new vscode.TreeItem(capability.canonical, vscode.TreeItemCollapsibleState.None);
    item.description = capability.id;
    const supported = Object.entries(capability.operations)
      .filter(([, status]) => status === "verified" || status === "implemented")
      .map(([operation, status]) => `${operation}: ${status}`)
      .join("\n");
    item.tooltip = new vscode.MarkdownString(
      `**${capability.id}**\n\nMaturity: ${capability.specification_maturity}\n\n${supported}`,
    );
    item.contextValue = "bsamCapability";
    return item;
  }

  getChildren(element?: TreeNode): TreeNode[] {
    if (!element) {
      return this.roots;
    }
    return element.type === "group" ? element.children : [];
  }
}
