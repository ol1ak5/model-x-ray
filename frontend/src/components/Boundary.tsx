import { Component, type ReactNode } from "react";

export default class Boundary extends Component<{ children: ReactNode; onReset: () => void }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="wrap fallback">
        <p className="alert" role="alert">
          Part of this page could not be drawn. The check itself is untouched.
        </p>
        <button type="button" className="pill green sm" onClick={this.props.onReset}>
          Start another check
        </button>
      </main>
    );
  }
}
