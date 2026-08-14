import { Component } from "react";
import { BTN_PRIMARY } from "../ui";

/**
 * Last line of defence for a render exception.
 *
 * Without one, any thrown error unmounted the whole tree and left a blank white
 * page — no message, no way back, and nothing in front of the user to suggest
 * reloading. A card and a reload button is a low bar, but it's a great deal
 * better than nothing.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error, info) {
    // Kept in the console rather than shown: the stack is for whoever is asked
    // to look into it, not for the person who just lost their place.
    console.error("Unhandled render error:", error, info?.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="min-h-screen flex items-center justify-center bg-stone-100 p-6">
        <div className="w-full max-w-sm bg-white rounded-2xl shadow-xl p-6 text-center">
          <h1 className="text-lg font-bold text-stone-900 font-display">Something went wrong</h1>
          <p className="text-sm text-stone-500 mt-2">
            The page couldn&apos;t be displayed. Reloading usually clears it.
          </p>
          <button
            onClick={() => window.location.reload()}
            className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}
          >
            Reload the page
          </button>
        </div>
      </div>
    );
  }
}
