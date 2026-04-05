import pandas as pd
from pathlib import Path
import numpy as np
from sklearn.metrics import confusion_matrix, classification_report, accuracy_score
from datetime import datetime
import json

# Paths to your files
PROJECT_ROOT = Path("/home/senatoma/coinfa/RugPullHunter").resolve()
DATASET1_PATH = PROJECT_ROOT / "dataset" / "Dataset_Excel" / "dataset.xlsx"
DATASET2_PATH = PROJECT_ROOT / "results" / "crpwarner_results_all.xlsx"
OUTPUT_DIR = PROJECT_ROOT / "results" / "metrics" / "crpwarner"

def load_datasets():
    """Load both datasets from Excel files."""
    print("Loading datasets...")
    df1 = pd.read_excel(DATASET1_PATH)
    df2 = pd.read_excel(DATASET2_PATH)
    
    print(f"\nDataset 1 shape: {df1.shape}")
    print(f"Dataset 1 columns: {list(df1.columns)}")
    print(f"\nDataset 2 shape: {df2.shape}")
    print(f"Dataset 2 columns: {list(df2.columns)}")
    
    # Show sample data to understand the structure
    print("\n" + "="*60)
    print("Sample from Dataset 1:")
    print(df1[['title', 'Smart Contract Online', 'Label']].head(3))
    
    print("\n" + "="*60)
    print("Sample from Dataset 2:")
    print(df2[['GroupID', 'Artifact', 'RugPull']].head(3))
    
    return df1, df2

def create_matching_key(df1, df2):
    """
    Try to create a matching key between datasets.
    This function will help identify how to match the two datasets.
    """
    print("\n" + "="*60)
    print("ANALYZING MATCHING POSSIBILITIES")
    print("="*60)
    
    # Check if there's a GroupID or ID column in dataset 1
    possible_id_cols_df1 = [col for col in df1.columns if 'id' in col.lower() or 'group' in col.lower()]
    print(f"\nPossible ID columns in Dataset 1: {possible_id_cols_df1}")
    
    # Check contract addresses
    if 'Smart Contract Online' in df1.columns:
        sample_contracts = df1['Smart Contract Online'].dropna().head(3).tolist()
        print(f"\nSample Smart Contracts from Dataset 1:")
        for sc in sample_contracts:
            print(f"  - {sc}")
    
    # Check GroupID in dataset 2
    if 'GroupID' in df2.columns:
        sample_groupids = df2['GroupID'].dropna().head(5).tolist()
        print(f"\nSample GroupIDs from Dataset 2: {sample_groupids}")
    
    if 'Artifact' in df2.columns:
        sample_artifacts = df2['Artifact'].dropna().head(5).tolist()
        print(f"\nSample Artifacts from Dataset 2: {sample_artifacts}")
    
    # Ask user for matching strategy
    print("\n" + "="*60)
    print("MATCHING STRATEGY")
    print("="*60)
    print("\nBased on your datasets, we need to determine how to match them.")
    print("Please check if:")
    print("1. The row index matches (row 0 in dataset1 = row 0 in dataset2)")
    print("2. There's a GroupID or identifier in dataset 1 that matches dataset 2")
    print("3. The Smart Contract addresses somehow map to GroupID or Artifact")

def preprocess_dataset1(df1):
    """Extract relevant columns from dataset 1 (ground truth)."""
    # Select relevant columns and add row index
    df1_clean = df1[['title', 'Smart Contract Online', 'Label']].copy()
    df1_clean['row_index'] = df1_clean.index
    
    # Normalize the Label column (scam = True, normal = False)
    df1_clean['is_scam'] = df1_clean['Label'].str.lower() == 'scam'
    
    print("\nDataset 1 (Ground Truth) - Label Distribution:")
    print(df1_clean['Label'].value_counts())
    
    return df1_clean

def preprocess_dataset2(df2):
    """Extract relevant columns from dataset 2 (crpwarner results)."""
    # Select relevant columns and add row index
    df2_clean = df2[['GroupID', 'Artifact', 'RugPull']].copy()
    df2_clean['row_index'] = df2_clean.index
    
    # Normalize the RugPull column
    df2_clean['predicted_scam'] = df2_clean['RugPull'].astype(bool)
    
    print("\nDataset 2 (CRPWarner Results) - RugPull Distribution:")
    print(df2_clean['RugPull'].value_counts())
    
    return df2_clean

def merge_datasets_by_index(df1_clean, df2_clean):
    """
    Merge datasets by row index (assuming they are aligned).
    This is the most straightforward approach if both datasets have the same order.
    """
    print("\n" + "="*60)
    print("MERGING DATASETS BY ROW INDEX")
    print("="*60)
    
    # Ensure both dataframes have the same length
    min_length = min(len(df1_clean), len(df2_clean))
    
    if len(df1_clean) != len(df2_clean):
        print(f"\n⚠ WARNING: Datasets have different lengths!")
        print(f"Dataset 1: {len(df1_clean)} rows")
        print(f"Dataset 2: {len(df2_clean)} rows")
        print(f"Using first {min_length} rows for comparison")
    
    # Merge by index
    merged = pd.merge(
        df1_clean.head(min_length),
        df2_clean.head(min_length),
        left_on='row_index',
        right_on='row_index',
        how='inner'
    )
    
    print(f"\nMerged dataset shape: {merged.shape}")
    print(f"Successfully merged {len(merged)} records")
    
    return merged

def evaluate_performance(merged_df):
    """Evaluate the performance of crpwarner tool."""
    y_true = merged_df['is_scam'].values
    y_pred = merged_df['predicted_scam'].values
    
    # Calculate metrics
    accuracy = accuracy_score(y_true, y_pred)
    cm = confusion_matrix(y_true, y_pred)
    
    print("\n" + "="*60)
    print("PERFORMANCE EVALUATION")
    print("="*60)
    
    print(f"\nAccuracy: {accuracy:.2%}")
    
    print("\nConfusion Matrix:")
    print("                  Predicted Normal  Predicted Scam")
    print(f"Actual Normal     {cm[0][0]:16d}  {cm[0][1]:14d}")
    print(f"Actual Scam       {cm[1][0]:16d}  {cm[1][1]:14d}")
    
    # Calculate additional metrics
    tn, fp, fn, tp = cm.ravel()
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0
    
    print("\nDetailed Metrics:")
    print(f"  Precision (Scam Detection): {precision:.2%}")
    print(f"  Recall (Scam Detection):    {recall:.2%}")
    print(f"  F1-Score:                   {f1_score:.2%}")
    print(f"  Specificity:                {specificity:.2%}")
    
    print("\nClassification Report:")
    print(classification_report(
        y_true, 
        y_pred, 
        target_names=['Normal', 'Scam'],
        digits=4
    ))
    
    # Store metrics for export
    metrics = {
        'accuracy': accuracy,
        'precision': precision,
        'recall': recall,
        'f1_score': f1_score,
        'specificity': specificity,
        'confusion_matrix': {
            'true_negatives': int(tn),
            'false_positives': int(fp),
            'false_negatives': int(fn),
            'true_positives': int(tp)
        }
    }
    
    return accuracy, cm, metrics

def detailed_comparison(merged_df):
    """Show detailed comparison for each contract."""
    print("\n" + "="*60)
    print("DETAILED COMPARISON (First 10 records)")
    print("="*60)
    
    for idx, row in merged_df.head(10).iterrows():
        match = "✓" if row['is_scam'] == row['predicted_scam'] else "✗"
        print(f"\n{match} {row['title']}")
        print(f"  GroupID: {row['GroupID']}")
        print(f"  Ground Truth: {row['Label']}")
        print(f"  CRPWarner Prediction: {'Scam (RugPull)' if row['predicted_scam'] else 'Normal'}")
        
        if row['is_scam'] != row['predicted_scam']:
            if row['is_scam']:
                print(f"  ⚠ FALSE NEGATIVE: Missed a scam!")
            else:
                print(f"  ⚠ FALSE POSITIVE: Incorrectly flagged as scam")

def analyze_misclassifications(merged_df):
    """Analyze patterns in misclassifications."""
    misclassified = merged_df[merged_df['is_scam'] != merged_df['predicted_scam']]
    
    print("\n" + "="*60)
    print("MISCLASSIFICATION ANALYSIS")
    print("="*60)
    
    false_negatives = misclassified[misclassified['is_scam'] == True]
    false_positives = misclassified[misclassified['is_scam'] == False]
    
    print(f"\nFalse Negatives (Missed Scams): {len(false_negatives)}")
    if len(false_negatives) > 0:
        print("Projects (first 10):")
        for _, row in false_negatives.head(10).iterrows():
            print(f"  - {row['title']} (GroupID: {row['GroupID']})")
    
    print(f"\nFalse Positives (Incorrectly Flagged): {len(false_positives)}")
    if len(false_positives) > 0:
        print("Projects (first 10):")
        for _, row in false_positives.head(10).iterrows():
            print(f"  - {row['title']} (GroupID: {row['GroupID']})")
    
    return false_negatives, false_positives

def generate_report_files(merged_df, metrics, df1, df2, false_negatives, false_positives):
    """Generate comprehensive report files for colleagues."""
    
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 1. Generate Excel Report with multiple sheets
    excel_path = OUTPUT_DIR / f"crpwarner_evaluation_report_{timestamp}.xlsx"
    with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
        # Summary sheet
        summary_data = {
            'Metric': [
                'Total Contracts Compared',
                'Accuracy',
                'Precision (Scam Detection)',
                'Recall (Scam Detection)',
                'F1-Score',
                'Specificity',
                '',
                'True Positives',
                'True Negatives',
                'False Positives',
                'False Negatives',
                '',
                'Correctly Classified',
                'Misclassified'
            ],
            'Value': [
                len(merged_df),
                f"{metrics['accuracy']:.2%}",
                f"{metrics['precision']:.2%}",
                f"{metrics['recall']:.2%}",
                f"{metrics['f1_score']:.2%}",
                f"{metrics['specificity']:.2%}",
                '',
                metrics['confusion_matrix']['true_positives'],
                metrics['confusion_matrix']['true_negatives'],
                metrics['confusion_matrix']['false_positives'],
                metrics['confusion_matrix']['false_negatives'],
                '',
                (merged_df['is_scam'] == merged_df['predicted_scam']).sum(),
                (merged_df['is_scam'] != merged_df['predicted_scam']).sum()
            ]
        }
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        
        # Detailed comparison sheet
        comparison_df = merged_df.copy()
        comparison_df['Match'] = comparison_df['is_scam'] == comparison_df['predicted_scam']
        comparison_df['Result'] = comparison_df.apply(
            lambda row: 'Correct' if row['Match'] else 
                       ('False Negative' if row['is_scam'] else 'False Positive'),
            axis=1
        )
        comparison_df = comparison_df[['title', 'GroupID', 'Label', 'predicted_scam', 'Match', 'Result']]
        comparison_df.columns = ['Project Name', 'GroupID', 'Ground Truth', 'CRPWarner Prediction', 'Correct', 'Classification']
        comparison_df.to_excel(writer, sheet_name='Detailed Comparison', index=False)
        
        # False Negatives sheet
        if len(false_negatives) > 0:
            fn_df = false_negatives[['title', 'GroupID', 'Label']].copy()
            fn_df.columns = ['Project Name', 'GroupID', 'Ground Truth']
            fn_df.to_excel(writer, sheet_name='False Negatives', index=False)
        
        # False Positives sheet
        if len(false_positives) > 0:
            fp_df = false_positives[['title', 'GroupID', 'Label']].copy()
            fp_df.columns = ['Project Name', 'GroupID', 'Ground Truth']
            fp_df.to_excel(writer, sheet_name='False Positives', index=False)
    
    print(f"\n✓ Excel report saved: {excel_path}")
    
    # 2. Generate Text Report
    txt_path = OUTPUT_DIR / f"crpwarner_evaluation_report_{timestamp}.txt"
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("CRPWARNER TOOL EVALUATION REPORT\n")
        f.write("="*80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("\n")
        
        f.write("DATASET INFORMATION\n")
        f.write("-"*80 + "\n")
        f.write(f"Ground Truth Dataset (Dataset 1): {df1.shape[0]} records\n")
        f.write(f"CRPWarner Results (Dataset 2): {df2.shape[0]} records\n")
        f.write(f"Common Contracts Compared: {len(merged_df)}\n")
        f.write("\n")
        
        f.write("PERFORMANCE METRICS\n")
        f.write("-"*80 + "\n")
        f.write(f"Accuracy:              {metrics['accuracy']:.2%}\n")
        f.write(f"Precision:             {metrics['precision']:.2%}\n")
        f.write(f"Recall (Sensitivity):  {metrics['recall']:.2%}\n")
        f.write(f"F1-Score:              {metrics['f1_score']:.2%}\n")
        f.write(f"Specificity:           {metrics['specificity']:.2%}\n")
        f.write("\n")
        
        f.write("CONFUSION MATRIX\n")
        f.write("-"*80 + "\n")
        f.write("                    Predicted Normal    Predicted Scam\n")
        f.write(f"Actual Normal       {metrics['confusion_matrix']['true_negatives']:16d}    {metrics['confusion_matrix']['false_positives']:14d}\n")
        f.write(f"Actual Scam         {metrics['confusion_matrix']['false_negatives']:16d}    {metrics['confusion_matrix']['true_positives']:14d}\n")
        f.write("\n")
        
        f.write("DETAILED RESULTS\n")
        f.write("-"*80 + "\n")
        f.write(f"True Positives (Correctly detected scams):  {metrics['confusion_matrix']['true_positives']}\n")
        f.write(f"True Negatives (Correctly detected normal): {metrics['confusion_matrix']['true_negatives']}\n")
        f.write(f"False Positives (Incorrectly flagged):      {metrics['confusion_matrix']['false_positives']}\n")
        f.write(f"False Negatives (Missed scams):             {metrics['confusion_matrix']['false_negatives']}\n")
        f.write("\n")
        
        if len(false_negatives) > 0:
            f.write("FALSE NEGATIVES (Missed Scams)\n")
            f.write("-"*80 + "\n")
            for _, row in false_negatives.iterrows():
                f.write(f"  • {row['title']}\n")
                f.write(f"    GroupID: {row['GroupID']}\n")
            f.write("\n")
        
        if len(false_positives) > 0:
            f.write("FALSE POSITIVES (Incorrectly Flagged as Scam)\n")
            f.write("-"*80 + "\n")
            for _, row in false_positives.iterrows():
                f.write(f"  • {row['title']}\n")
                f.write(f"    GroupID: {row['GroupID']}\n")
            f.write("\n")
    
    print(f"✓ Text report saved: {txt_path}")
    
    # 3. Generate JSON Report
    json_path = OUTPUT_DIR / f"crpwarner_evaluation_report_{timestamp}.json"
    json_data = {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'ground_truth_records': int(df1.shape[0]),
            'crpwarner_records': int(df2.shape[0]),
            'compared_contracts': int(len(merged_df))
        },
        'metrics': metrics,
        'false_negatives_count': len(false_negatives),
        'false_positives_count': len(false_positives)
    }
    
    with open(json_path, 'w') as f:
        json.dump(json_data, f, indent=2, default=str)
    
    print(f"✓ JSON report saved: {json_path}")
    
    # 4. Generate CSV Report
    csv_path = OUTPUT_DIR / f"crpwarner_comparison_{timestamp}.csv"
    comparison_df.to_csv(csv_path, index=False)
    print(f"✓ CSV report saved: {csv_path}")
    
    return excel_path, txt_path, json_path, csv_path

def main():
    """Main function to run the comparison."""
    print("="*60)
    print("CRPWARNER TOOL EVALUATION")
    print("="*60)
    
    # Load datasets
    df1, df2 = load_datasets()
    
    # Analyze matching possibilities
    create_matching_key(df1, df2)
    
    # Ask user to confirm matching strategy
    print("\n" + "="*60)
    print("PROCEEDING WITH INDEX-BASED MATCHING")
    print("="*60)
    print("Assuming that row N in Dataset 1 corresponds to row N in Dataset 2")
    print("Press Ctrl+C to abort if this is incorrect")
    
    # Preprocess
    df1_clean = preprocess_dataset1(df1)
    df2_clean = preprocess_dataset2(df2)
    
    # Merge datasets by index
    merged_df = merge_datasets_by_index(df1_clean, df2_clean)
    
    if len(merged_df) == 0:
        print("\n⚠ WARNING: No records to compare!")
        return
    
    # Evaluate performance
    accuracy, cm, metrics = evaluate_performance(merged_df)
    
    # Detailed comparison
    detailed_comparison(merged_df)
    
    # Analyze misclassifications
    false_negatives, false_positives = analyze_misclassifications(merged_df)
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total contracts compared: {len(merged_df)}")
    print(f"Overall accuracy: {accuracy:.2%}")
    print(f"Correctly classified: {(merged_df['is_scam'] == merged_df['predicted_scam']).sum()}")
    print(f"Misclassified: {(merged_df['is_scam'] != merged_df['predicted_scam']).sum()}")
    
    # Generate report files
    print("\n" + "="*60)
    print("GENERATING REPORT FILES")
    print("="*60)
    excel_path, txt_path, json_path, csv_path = generate_report_files(
        merged_df, metrics, df1, df2, false_negatives, false_positives
    )
    
    print("\n" + "="*60)
    print("REPORT FILES GENERATED")
    print("="*60)
    print(f"\nAll reports saved in: {OUTPUT_DIR}")
    print("\nFiles created:")
    print(f"  1. Excel Report (multi-sheet): {excel_path.name}")
    print(f"  2. Text Report (readable):     {txt_path.name}")
    print(f"  3. JSON Report (structured):   {json_path.name}")
    print(f"  4. CSV Report (comparison):    {csv_path.name}")
    print("\nYou can now share these files with your colleagues!")

if __name__ == "__main__":
    main()