import { Page, Card, Button } from "@shopify/polaris";

export function ProductPage() {
  return (
    <Page title="Products">
      <s-card>
        <s-button>Click me</s-button>
      </s-card>
      <Card>
        <Button>Also click me</Button>
      </Card>
    </Page>
  );
}
