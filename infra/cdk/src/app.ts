import { App, DefaultStackSynthesizer, Stack } from "aws-cdk-lib";

/** An environment-agnostic, resource-free scaffold. No lookups or application assets. */
export function createFoundation(outdir?: string) {
  const app = new App({
    outdir,
    analyticsReporting: false,
    treeMetadata: false,
  });
  const stack = new Stack(app, "EdgeEagleFoundation", {
    // No resources or assets need a bootstrap version in this local scaffold.
    // Revisit this when actual deployment resources are introduced.
    synthesizer: new DefaultStackSynthesizer({
      generateBootstrapVersionRule: false,
    }),
  });
  return { app, stack };
}
