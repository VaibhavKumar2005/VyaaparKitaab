export const CATEGORY_TAXONOMY: Record<string, string[]> = {
  Food: ['Grocery', 'Restaurants', 'Delivery', 'Cafe & Beverages', 'General Food'],
  Shopping: ['Electronics', 'Clothing', 'Household', 'Books & Stationery', 'General Shopping'],
  Transport: ['Fuel', 'Cab', 'Public Transport', 'General Transport'],
  'Utilities & Bills': [
    'Electricity & Power',
    'Telecom & Internet',
    'Water & Gas',
    'Rent & Society',
    'General Bills',
  ],
  'Health & Medical': ['Pharmacy & Medicines', 'Clinic & Diagnostics', 'General Health'],
  Entertainment: ['Streaming & OTT', 'Movies & Events', 'General Entertainment'],
  'Business & MSME': [
    'Retail Store Sale',
    'Wholesale Inventory',
    'Supplier Settlement',
    'Services & SaaS',
  ],
  'Financial & Transfers': [
    'Salary & Credits',
    'Refund & Cashback',
    'Peer Transfers',
    'EMI & Loans',
    'General Transfer',
  ],
  Other: ['General'],
};

export const TAXONOMY_CATEGORIES = Object.keys(CATEGORY_TAXONOMY);
