'use client';

import { AccountActions } from './account-actions';

interface Props {
  externalId: string;
  platform: string;
  handle: string;
  csvText: string;
}

/**
 * Thin client wrapper that lets the server pre-build the CSV string and
 * hand it to the client component as a stable closure. Saves us a round
 * trip when the user hits "Export → CSV".
 */
export function AccountActionsClient({ externalId, platform, handle, csvText }: Props) {
  return (
    <AccountActions
      externalId={externalId}
      platform={platform}
      handle={handle}
      csvRows={() => csvText}
    />
  );
}
