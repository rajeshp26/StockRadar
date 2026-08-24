#!/usr/bin/env python3
"""Migrate 3 investors to correct CIKs in DB.
Preserves investor_id to maintain referential integrity.
Uses project's config pattern (no hardcoded credentials).
"""
import sys

sys.path.insert(0, '.')

import logging

from database import supabase

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Migration mappings: Old CIK → (New CIK, New Firm Name)
MIGRATIONS = {
    "0001173334": ("0001549575", "DALAL STREET LLC"),
    "0001325920": ("0001418814", "VALUEACT HOLDINGS, L.P."),
    "0000872323": ("0001406950", "HARRIS ASSOCIATES LP"),
}

def migrate_cik(old_cik, new_cik, new_firm):
    """Update CIK in-place, preserving investor_id."""
    try:
        # Check if old record exists
        result = supabase.table('institutional_investors').select('*').eq('cik', old_cik).execute()

        if not result.data:
            logger.warning(f"Old CIK {old_cik} not found in DB, skipping")
            return False

        inv = result.data[0]
        inv_id = inv['investor_id']
        old_name = inv['investor_name']

        # Check if new CIK already exists (duplicate check)
        existing = supabase.table('institutional_investors').select('*').eq('cik', new_cik).execute()

        if existing.data:
            new_id = existing.data[0]['investor_id']
            # Check if new record has holdings
            new_holdings = supabase.table('institutional_holdings').select('holding_id').eq('investor_id', new_id).execute()

            if not new_holdings.data or len(new_holdings.data) == 0:
                # Safe to delete empty new record
                supabase.table('institutional_investors').delete().eq('investor_id', new_id).execute()
                logger.info(f"  Deleted empty new record (ID={new_id})")
            else:
                logger.error(f"New CIK {new_cik} has {len(new_holdings.data)} holdings - manual intervention needed!")
                return False

        # Update CIK in-place (preserve investor_id and all holdings)
        supabase.table('institutional_investors').update({
            'cik': new_cik,
            'firm_name': new_firm,
        }).eq('investor_id', inv_id).execute()

        logger.info(f"[OK] Migrated: {old_name} (CIK {old_cik} → {new_cik}, investor_id={inv_id} preserved)")
        return True

    except Exception as e:
        logger.error(f"[FAIL] Failed to migrate {old_cik}: {e}")
        return False

def verify_migration():
    """Verify all migrations completed successfully."""
    logger.info("=== VERIFICATION ===")
    for old_cik, (new_cik, _) in MIGRATIONS.items():
        # Old CIK should not exist
        old = supabase.table('institutional_investors').select('investor_id').eq('cik', old_cik).execute()
        # New CIK should exist
        new = supabase.table('institutional_investors').select('*').eq('cik', new_cik).execute()

        if not old.data and new.data:
            inv = new.data[0]
            # Count holdings
            holdings = supabase.table('institutional_holdings').select('holding_id').eq('investor_id', inv['investor_id']).execute()
            logger.info(f"[OK] {new_cik}: {inv['investor_name']} (holdings: {len(holdings.data)})")
        else:
            logger.error(f"[FAIL] Migration incomplete for {old_cik}")

def main():
    logger.info("="*60)
    logger.info("CIK MIGRATION SCRIPT (13F-HR Only)")
    logger.info("="*60)

    # Step 1: Verify pre-conditions
    logger.info("\n[Step 1] Checking pre-conditions...")
    for old_cik, (new_cik, firm) in MIGRATIONS.items():
        old = supabase.table('institutional_investors').select('investor_id', 'investor_name').eq('cik', old_cik).execute()
        new = supabase.table('institutional_investors').select('investor_id').eq('cik', new_cik).execute()

        if old.data:
            logger.info(f"  Found: CIK {old_cik} → {old.data[0]['investor_name']}")
        else:
            logger.warning(f"  Not found: CIK {old_cik}")

        if new.data:
            logger.warning(f"  Already exists: CIK {new_cik} (ID={new.data[0]['investor_id']})")

    # Step 2: Auto-continue (skip prompt for automated run)
    logger.info("\n[Step 2] Auto-continuing migration...")

    # Step 3: Execute migrations
    logger.info("\n[Step 3] Migrating...")
    success_count = 0
    for old_cik, (new_cik, firm) in MIGRATIONS.items():
        if migrate_cik(old_cik, new_cik, firm):
            success_count += 1

    # Step 4: Verify
    logger.info(f"\n[Step 4] Verification ({success_count}/{len(MIGRATIONS)} successful)")
    verify_migration()

    logger.info("\n" + "="*60)
    logger.info("MIGRATION COMPLETE")
    logger.info("="*60)

if __name__ == "__main__":
    main()
