import pandas as pd

print("🚀 INITIALIZING ENTERPRISE MHE PROCUREMENT ENGINE (AHP Core)...\n")

# ==========================================
# PHASE 1: DATA INGESTION
# ==========================================
df = pd.read_csv('mhe_pqcdms_data.csv')
vendors = ['Godrej', 'Toyota', 'Jungheinrich', 'Linde']

def get_param(param_name):
    return df[df['Parameter'] == param_name][vendors].values.astype(float)[0]

# Extracting Metrics
capex = get_param('Total Landed CapEx (INR)')
total_amc = get_param('Year 2 AMC Charges (INR)') + get_param('Year 3 AMC Charges (INR)') + get_param('Year 4 AMC Charges (INR)') + get_param('Year 5 AMC Charges (INR)')
battery_cost = get_param('Estimated Battery Replacement Cost (INR)')
lead_time = get_param('Manufacturing Lead Time (Weeks)')
tech_score = get_param('Technical Compliance Score (%)')

# Safety Check
auto_decel_raw = df[df['Parameter'] == 'Auto-Deceleration Control'][vendors].values[0]
auto_decel_binary = [1 if str(val).strip().lower() == 'yes' else 0 for val in auto_decel_raw]

# ==========================================
# PHASE 2: ADVANCED MATH (TCO & AHP SCORING)
# ==========================================
safety_penalty = [(1 - val) * 50000 for val in auto_decel_binary]
tco = capex + total_amc + battery_cost + safety_penalty

results = pd.DataFrame({
    'Vendor': vendors,
    '5_Year_TCO_INR': tco,
    'Lead_Time_Weeks': lead_time,
    'Tech_Score': tech_score,
    'Safety_Score': [val * 100 for val in auto_decel_binary]
})

# AHP Weighted Scoring (Cost: 40%, Tech: 30%, Delivery: 20%, Safety: 10%)
results['Norm_Cost'] = (results['5_Year_TCO_INR'].min() / results['5_Year_TCO_INR']) * 100
results['Norm_Delivery'] = (results['Lead_Time_Weeks'].min() / results['Lead_Time_Weeks']) * 100

results['Final_AHP_Score'] = (
    (results['Norm_Cost'] * 0.40) +
    (results['Tech_Score'] * 0.30) +
    (results['Norm_Delivery'] * 0.20) +
    (results['Safety_Score'] * 0.10)
)

# Sort by the highest score to find the winner
results = results.sort_values(by='Final_AHP_Score', ascending=False).reset_index(drop=True)

# Export to CSV
results.to_csv('MHE_AHP_Decision_Matrix.csv', index=False)

print("✅ PHASE 2 COMPLETE: Multi-Criteria Decision Math Executed.")
print("\n--- FINAL VENDOR RANKING ---")
print(results[['Vendor', 'Final_AHP_Score', '5_Year_TCO_INR', 'Lead_Time_Weeks']])
print("\n🎯 PIPELINE FINISHED. File 'MHE_AHP_Decision_Matrix.csv' has been generated!")