# Pharmacy Stock Notification

Low Stock Alert System for Odoo 18 Community Edition

## Features
- Minimum quantity field on products
- Automatic notifications when stock falls below minimum
- Activity tracking for pharmacy group users
- Acknowledge and resolve notification system
- Integration with sale orders

## Installation
1. Copy this folder to your Odoo addons directory
2. Restart Odoo server
3. Go to Apps → Update Apps List
4. Search for "Pharmacy Stock Notification"
5. Click Install

## Configuration
1. Go to Settings → Users & Companies → Groups
2. Assign users to "Pharmacy User" group
3. These users will receive low stock notifications

## Usage
1. Go to Inventory → Products
2. Open a product
3. Go to Inventory tab
4. Enable "Enable Low Stock Alert" checkbox
5. Set "Minimum Stock Quantity" (e.g., 10 units)
6. When sales order is confirmed and stock falls below minimum:
   - Notification is automatically created
   - Pharmacy users receive activity alert
   - Notification appears in "Low Stock Alerts" menu

## Support
For issues or questions, contact your system administrator.
