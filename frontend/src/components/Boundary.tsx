import { Component, type ReactNode } from "react";

import Alert from "./Alert";
import Button from "./Button";
import styles from "./Boundary.module.css";

export default class Boundary extends Component<{ children: ReactNode; onReset: () => void }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className={styles.fallback}>
        <Alert>Part of this view could not be drawn. The check itself is untouched.</Alert>
        <Button onClick={this.props.onReset}>Start another check</Button>
      </div>
    );
  }
}
