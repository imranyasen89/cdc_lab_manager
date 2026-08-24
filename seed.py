from datetime import datetime, date, timedelta
from app import create_app, db
from app.models import User, Branch, Department, TATRule, OutsourcedLab, SampleRequest, Sample, Task, StatusHistory, LocationRecord

def seed_data():
    app = create_app()
    with app.app_context():
        print("Recreating database tables...")
        db.drop_all()
        db.create_all()
        
        print("Seeding master configurations...")
        
        # 1. Branches (with lat/lng coordinates in Islamabad)
        g8_hq = Branch(name="G-8 Main Lab (HQ)", code="G8", address="G-8 Markaz, Islamabad", latitude=33.6811, longitude=73.0361)
        g11_branch = Branch(name="G-11 Collection Center", code="G11", address="G-11 Markaz, Islamabad", latitude=33.6822, longitude=73.0076)
        g10_branch = Branch(name="G-10 Branch Office", code="G10", address="G-10 Markaz, Islamabad", latitude=33.6896, longitude=73.0245)
        g13_branch = Branch(name="G-13 Collection Hub", code="G13", address="G-13 Markaz, Islamabad", latitude=33.6521, longitude=73.0674)
        
        db.session.add_all([g8_hq, g11_branch, g10_branch, g13_branch])
        db.session.commit()
        
        # 2. Departments
        hem = Department(name="Hematology", description="Cell counting and blood work analysis")
        bio = Department(name="Biochemistry", description="Chemical panels and serum analysis")
        mic = Department(name="Microbiology", description="Swab cultures and pathogen detection")
        
        db.session.add_all([hem, bio, mic])
        db.session.commit()
        
        # 3. TAT Rules (priority rules in minutes)
        routine_tat = TATRule(priority="Routine", max_tat_minutes=360, description="Standard diagnostic samples (6 hours limit)")
        urgent_tat = TATRule(priority="Urgent", max_tat_minutes=180, description="Urgent medical samples (3 hours limit)")
        emergency_tat = TATRule(priority="Emergency", max_tat_minutes=120, description="Critical stats diagnostic samples (2 hours limit)")
        
        db.session.add_all([routine_tat, urgent_tat, emergency_tat])
        db.session.commit()
        
        # 4. Outsourced Labs
        excel = OutsourcedLab(name="Excel Diagnostics Labs", contact_info="+92-51-111-222-333", address="F-8 Markaz, Islamabad")
        idc = OutsourcedLab(name="Islamabad Diagnostic Center", contact_info="+92-51-225-1212", address="G-8 Markaz, Islamabad")
        
        db.session.add_all([excel, idc])
        db.session.commit()
        
        print("Registering employee accounts...")
        
        # 5. User Accounts
        users = [
            User(name="Super Administrator", username="admin", employee_id="EMP-1001", role="ADMIN", phone="0333-1111111", email="admin@cdc.com", status=True, joining_date=date.today()),
            User(name="Dr. Ali Manager", username="manager", employee_id="EMP-1002", role="MANAGER", phone="0333-2222222", email="ali@cdc.com", status=True, joining_date=date.today()),
            User(name="Kamran Supervisor", username="supervisor", employee_id="EMP-1003", role="SUPERVISOR", phone="0333-3333333", email="kamran@cdc.com", status=True, joining_date=date.today()),
            User(name="Zahra Branch Staff (G11)", username="branch11", employee_id="EMP-1004", role="BRANCH_STAFF", phone="0333-4444444", email="zahra@cdc.com", branch_id=g11_branch.id, status=True, joining_date=date.today()),
            User(name="Sana Technologist", username="tech", employee_id="EMP-1005", role="LAB_STAFF", phone="0333-5555555", email="sana@cdc.com", department_id=bio.id, status=True, joining_date=date.today()),
            User(name="Dr. Haris Verifier", username="verifier", employee_id="EMP-1006", role="VERIFIER", phone="0333-6666666", email="haris@cdc.com", status=True, joining_date=date.today()),
            # Riders
            User(name="Ahmed Courier", username="rider1", employee_id="EMP-2001", role="RIDER", phone="0345-1111111", email="ahmed@courier.com", status=True, joining_date=date.today()),
            User(name="Bilal Courier", username="rider2", employee_id="EMP-2002", role="RIDER", phone="0345-2222222", email="bilal@courier.com", status=True, joining_date=date.today()),
            User(name="Hamza Courier", username="rider3", employee_id="EMP-2003", role="RIDER", phone="0345-3333333", email="hamza@courier.com", status=True, joining_date=date.today())
        ]
        
        # Set passwords matching username + '123'
        for u in users:
            u.set_password(u.username + "123")
            db.session.add(u)
            
        db.session.commit()
        
        print("Generating mock requests at different workflow stages...")
        
        # Mock requests details
        now = datetime.utcnow()
        
        # Helper function to create status logs
        def add_log(req_id, status, user_id, delta_mins, remarks=None, location=None):
            timestamp = now - timedelta(minutes=delta_mins)
            history = StatusHistory(
                request_id=req_id,
                status=status,
                changed_by_id=user_id,
                timestamp=timestamp,
                remarks=remarks,
                location=location
            )
            db.session.add(history)
            
        # Helper to create active/completed tasks
        def add_task(task_type, req_id, user_id, role, status, created_delta, start_delta=None, comp_delta=None):
            task = Task(
                task_type=task_type,
                request_id=req_id,
                assigned_user_id=user_id,
                assigned_role=role,
                created_time=now - timedelta(minutes=created_delta),
                start_time=now - timedelta(minutes=start_delta) if start_delta else None,
                completion_time=now - timedelta(minutes=comp_delta) if comp_delta else None,
                status=status
            )
            db.session.add(task)
            
        # Request 1: Stage 'Pickup Requested' (New)
        req1_id = "RIC-G11-20260820-000001"
        req1 = SampleRequest(
            id=req1_id, patient_name="David Miller", gender="Male", patient_id="MRN-00101",
            priority="Emergency", branch_id=g11_branch.id, created_by_id=users[3].id,
            status="Pickup Requested", created_at=now - timedelta(minutes=15)
        )
        db.session.add(req1)
        db.session.add(Sample(request_id=req1_id, sample_type="Blood (EDTA)", quantity=2))
        add_log(req1_id, "Pickup Requested", users[3].id, 15, "Request created. Patient suffering from high fever.", "G-11 Collection Center")
        add_task("PICKUP", req1_id, None, "RIDER", "PENDING", 15)
        
        # Request 2: Stage 'Rider Assigned' (Assigned to Rider Ahmed)
        req2_id = "RIC-G11-20260820-000002"
        req2 = SampleRequest(
            id=req2_id, patient_name="Sarah Connor", gender="Female", patient_id="MRN-00102",
            priority="Routine", branch_id=g11_branch.id, created_by_id=users[3].id,
            status="Rider Assigned", created_at=now - timedelta(minutes=45)
        )
        db.session.add(req2)
        db.session.add(Sample(request_id=req2_id, sample_type="Urine", quantity=1))
        add_log(req2_id, "Pickup Requested", users[3].id, 45, "Routine urinalysis test.", "G-11 Collection Center")
        add_log(req2_id, "Rider Assigned", users[2].id, 35, "Assigned to Ahmed Courier", "G-8 Main Lab Supervisor Desk")
        add_task("PICKUP", req2_id, users[6].id, None, "IN_PROGRESS", 45, 35)
        # Location log
        db.session.add(LocationRecord(request_id=req2_id, rider_id=users[6].id, latitude=33.6820, longitude=73.0075, event_name="ACCEPT_PICKUP", timestamp=now - timedelta(minutes=35)))

        # Request 3: Stage 'Sample Collected' (Rider Bilal carrying)
        req3_id = "RIC-G10-20260820-000003"
        req3 = SampleRequest(
            id=req3_id, patient_name="Arthur Pendragon", gender="Male",
            priority="Urgent", branch_id=g10_branch.id, created_by_id=users[0].id,
            status="Sample Collected", created_at=now - timedelta(minutes=80)
        )
        db.session.add(req3)
        db.session.add(Sample(request_id=req3_id, sample_type="Blood (Serum)", quantity=1))
        add_log(req3_id, "Pickup Requested", users[0].id, 80, "Urgent Lipid Profile", "G-10 Branch Office")
        add_log(req3_id, "Rider Assigned", users[7].id, 70, "Self-assigned by Bilal", "GPS Location")
        add_log(req3_id, "Sample Collected", users[7].id, 45, "Urgent serum sample secured.", "G-10 Branch Office")
        add_task("PICKUP", req3_id, users[7].id, None, "COMPLETED", 80, 70, 45)
        add_task("TRANSPORT", req3_id, users[7].id, None, "IN_PROGRESS", 45, 45)
        db.session.add(LocationRecord(request_id=req3_id, rider_id=users[7].id, latitude=33.6896, longitude=73.0245, event_name="CONFIRM_COLLECTION", timestamp=now - timedelta(minutes=45)))
        db.session.add(LocationRecord(request_id=req3_id, rider_id=users[7].id, latitude=33.6850, longitude=73.0310, event_name="PERIODIC_UPDATE", timestamp=now - timedelta(minutes=25)))

        # Request 4: Stage 'Arrived at G-8' (Rider Hamza delivered)
        req4_id = "RIC-G13-20260820-000004"
        req4 = SampleRequest(
            id=req4_id, patient_name="Clark Kent", gender="Male",
            priority="Routine", branch_id=g13_branch.id, created_by_id=users[0].id,
            status="Arrived at G-8", created_at=now - timedelta(minutes=95)
        )
        db.session.add(req4)
        db.session.add(Sample(request_id=req4_id, sample_type="Swab", quantity=2))
        add_log(req4_id, "Pickup Requested", users[0].id, 95, "Covid qPCR swab.", "G-13 Collection Hub")
        add_log(req4_id, "Rider Assigned", users[8].id, 90, "Self-assigned by Hamza", "GPS Location")
        add_log(req4_id, "Sample Collected", users[8].id, 70, "PCR swab collected.", "G-13 Collection Hub")
        add_log(req4_id, "Arrived at G-8", users[8].id, 20, "Delivered to Main Lab gate.", "G-8 Main Lab Gate")
        add_task("PICKUP", req4_id, users[8].id, None, "COMPLETED", 95, 90, 70)
        add_task("TRANSPORT", req4_id, users[8].id, None, "COMPLETED", 70, 70, 20)
        add_task("RECEIVE", req4_id, None, "LAB_STAFF", "PENDING", 20)
        db.session.add(LocationRecord(request_id=req4_id, rider_id=users[8].id, latitude=33.6521, longitude=73.0674, event_name="CONFIRM_COLLECTION", timestamp=now - timedelta(minutes=70)))
        db.session.add(LocationRecord(request_id=req4_id, rider_id=users[8].id, latitude=33.6811, longitude=73.0361, event_name="ARRIVE_G8", timestamp=now - timedelta(minutes=20)))

        # Request 5: Stage 'Received at G-8' (Tech Sana logged receiving)
        req5_id = "RIC-G11-20260820-000005"
        req5 = SampleRequest(
            id=req5_id, patient_name="Bruce Wayne", gender="Male",
            priority="Routine", branch_id=g11_branch.id, created_by_id=users[3].id,
            status="Received at G-8", created_at=now - timedelta(minutes=120)
        )
        db.session.add(req5)
        db.session.add(Sample(request_id=req5_id, sample_type="Blood (Serum)", quantity=1))
        add_log(req5_id, "Pickup Requested", users[3].id, 120, "Biochemical Profile", "G-11 Collection Center")
        add_log(req5_id, "Rider Assigned", users[6].id, 115, "Assigned to Ahmed", "HQ Desk")
        add_log(req5_id, "Sample Collected", users[6].id, 90, "Blood Serum sample secured", "G-11 Collection Center")
        add_log(req5_id, "Arrived at G-8", users[6].id, 65, "Delivered", "G-8 Entrance")
        add_log(req5_id, "Received at G-8", users[4].id, 60, "Accepted. Condition: Good. Qty: 1.", "G-8 Main Lab Receiving Desk")
        add_task("PICKUP", req5_id, users[6].id, None, "COMPLETED", 120, 115, 90)
        add_task("TRANSPORT", req5_id, users[6].id, None, "COMPLETED", 90, 90, 65)
        add_task("RECEIVE", req5_id, users[4].id, None, "COMPLETED", 65, 65, 60)
        add_task("PROCESS", req5_id, None, "LAB_STAFF", "PENDING", 60)

        # Request 6: Stage 'Processing' (Tech Sana processing)
        req6_id = "RIC-G11-20260820-000006"
        req6 = SampleRequest(
            id=req6_id, patient_name="Barry Allen", gender="Male",
            priority="Emergency", branch_id=g11_branch.id, created_by_id=users[3].id,
            status="Processing", created_at=now - timedelta(minutes=100)
        )
        db.session.add(req6)
        db.session.add(Sample(request_id=req6_id, sample_type="Blood (EDTA)", quantity=2))
        add_log(req6_id, "Pickup Requested", users[3].id, 100, "Stat CBC required.", "G-11 Collection Center")
        add_log(req6_id, "Rider Assigned", users[6].id, 95, "Assigned to Ahmed", "HQ Desk")
        add_log(req6_id, "Sample Collected", users[6].id, 80, "Stat EDTA tubes secured.", "G-11 Collection Center")
        add_log(req6_id, "Arrived at G-8", users[6].id, 60, "Delivered", "G-8 Entrance")
        add_log(req6_id, "Received at G-8", users[4].id, 55, "Accepted in Icebox. Condition: Good.", "G-8 Main Lab Receiving")
        add_log(req6_id, "Processing", users[4].id, 50, "Centrifugation completed. Run biochemistry analyzer.", "Biochemistry Bench")
        add_task("PICKUP", req6_id, users[6].id, None, "COMPLETED", 100, 95, 80)
        add_task("TRANSPORT", req6_id, users[6].id, None, "COMPLETED", 80, 80, 60)
        add_task("RECEIVE", req6_id, users[4].id, None, "COMPLETED", 60, 60, 55)
        add_task("PROCESS", req6_id, users[4].id, None, "IN_PROGRESS", 55, 50)

        # Request 7: Stage 'Pending Verification' (Tech entered result, Verifier pending)
        req7_id = "RIC-G13-20260820-000007"
        req7 = SampleRequest(
            id=req7_id, patient_name="Diana Prince", gender="Female",
            priority="Urgent", branch_id=g13_branch.id, created_by_id=users[0].id,
            status="Pending Verification", created_at=now - timedelta(minutes=150)
        )
        db.session.add(req7)
        db.session.add(Sample(request_id=req7_id, sample_type="Urine", quantity=1))
        add_log(req7_id, "Pickup Requested", users[0].id, 150, "Urgent urinalysis", "G-13 Hub")
        add_log(req7_id, "Rider Assigned", users[8].id, 140, "Self-assigned Hamza", "GPS")
        add_log(req7_id, "Sample Collected", users[8].id, 110, "Urinalysis sample collected.", "G-13 Hub")
        add_log(req7_id, "Arrived at G-8", users[8].id, 80, "Arrived at main entrance.", "G-8 Gate")
        add_log(req7_id, "Received at G-8", users[4].id, 75, "Accepted sample.", "Receiving Desk")
        add_log(req7_id, "Processing", users[4].id, 70, "Analyses running.", "Urinalysis Bench")
        add_log(req7_id, "Processing Completed", users[4].id, 40, "Diagnostic tests finished.", "Urinalysis Bench")
        add_log(req7_id, "Pending Verification", users[4].id, 35, "Result entered. Ref/Report No: REF-99023. Remarks: No glucose, protein traces found.", "HIMS Desk")
        add_task("PICKUP", req7_id, users[8].id, None, "COMPLETED", 150, 140, 110)
        add_task("TRANSPORT", req7_id, users[8].id, None, "COMPLETED", 110, 110, 80)
        add_task("RECEIVE", req7_id, users[4].id, None, "COMPLETED", 80, 80, 75)
        add_task("PROCESS", req7_id, users[4].id, None, "COMPLETED", 75, 70, 40)
        add_task("ENTER_RESULT", req7_id, users[4].id, None, "COMPLETED", 40, 40, 35)
        add_task("VERIFY", req7_id, None, "VERIFIER", "PENDING", 35)

        # Request 8: Stage 'Verified' (Approved by Verifier, Ready for delivery)
        req8_id = "RIC-G10-20260820-000008"
        req8 = SampleRequest(
            id=req8_id, patient_name="Tony Stark", gender="Male",
            priority="Routine", branch_id=g10_branch.id, created_by_id=users[0].id,
            status="Verified", created_at=now - timedelta(minutes=240)
        )
        db.session.add(req8)
        db.session.add(Sample(request_id=req8_id, sample_type="Blood (Serum)", quantity=1))
        add_log(req8_id, "Pickup Requested", users[0].id, 240, "Thyroid Profile", "G-10 Office")
        add_log(req8_id, "Rider Assigned", users[7].id, 230, "Self-assigned Bilal", "GPS")
        add_log(req8_id, "Sample Collected", users[7].id, 200, "Thyroid profile blood collected.", "G-10 Office")
        add_log(req8_id, "Arrived at G-8", users[7].id, 160, "Arrived", "G-8 Gate")
        add_log(req8_id, "Received at G-8", users[4].id, 155, "Accepted.", "Receiving")
        add_log(req8_id, "Processing", users[4].id, 150, "Analyzer started.", "Immunoassay Bench")
        add_log(req8_id, "Processing Completed", users[4].id, 110, "Finished analysis.", "Immunoassay Bench")
        add_log(req8_id, "Pending Verification", users[4].id, 100, "Result entered. Ref: REF-99024. Remarks: Normal T3, T4, TSH.", "HIMS Desk")
        add_log(req8_id, "Verified", users[5].id, 80, "Report approved. Findings verified.", "Verifier Desk")
        add_task("PICKUP", req8_id, users[7].id, None, "COMPLETED", 240, 230, 200)
        add_task("TRANSPORT", req8_id, users[7].id, None, "COMPLETED", 200, 200, 160)
        add_task("RECEIVE", req8_id, users[4].id, None, "COMPLETED", 160, 160, 155)
        add_task("PROCESS", req8_id, users[4].id, None, "COMPLETED", 155, 150, 110)
        add_task("ENTER_RESULT", req8_id, users[4].id, None, "COMPLETED", 110, 110, 100)
        add_task("VERIFY", req8_id, users[5].id, None, "COMPLETED", 100, 100, 80)
        add_task("DELIVER", req8_id, None, "BRANCH_STAFF", "PENDING", 80)

        # Request 9: Stage 'Completed' (Finished / Report Delivered)
        req9_id = "RIC-G11-20260820-000009"
        req9 = SampleRequest(
            id=req9_id, patient_name="Peter Parker", gender="Male",
            priority="Routine", branch_id=g11_branch.id, created_by_id=users[3].id,
            status="Completed", created_at=now - timedelta(minutes=300)
        )
        db.session.add(req9)
        db.session.add(Sample(request_id=req9_id, sample_type="Blood (Serum)", quantity=1))
        add_log(req9_id, "Pickup Requested", users[3].id, 300, "Complete Biochemical Panel", "G-11 Branch")
        add_log(req9_id, "Rider Assigned", users[6].id, 290, "Assigned to Ahmed", "HQ")
        add_log(req9_id, "Sample Collected", users[6].id, 260, "Blood Serum sample secured", "G-11 Branch")
        add_log(req9_id, "Arrived at G-8", users[6].id, 220, "Arrived", "G-8 Gate")
        add_log(req9_id, "Received at G-8", users[4].id, 215, "Accepted.", "Receiving")
        add_log(req9_id, "Processing", users[4].id, 210, "Analyzer started.", "Chemistry Bench")
        add_log(req9_id, "Processing Completed", users[4].id, 160, "Finished analysis.", "Chemistry Bench")
        add_log(req9_id, "Pending Verification", users[4].id, 150, "Result entered. Ref: REF-99025. Remarks: Glucose high.", "HIMS Desk")
        add_log(req9_id, "Verified", users[5].id, 130, "Report approved. Findings verified.", "Verifier Desk")
        add_log(req9_id, "Completed", users[3].id, 100, "Delivered via Online Portal to Patient. Remarks: Patient downloaded report.", "Online Portal")
        add_task("PICKUP", req9_id, users[6].id, None, "COMPLETED", 300, 290, 260)
        add_task("TRANSPORT", req9_id, users[6].id, None, "COMPLETED", 260, 260, 220)
        add_task("RECEIVE", req9_id, users[4].id, None, "COMPLETED", 220, 220, 215)
        add_task("PROCESS", req9_id, users[4].id, None, "COMPLETED", 215, 210, 160)
        add_task("ENTER_RESULT", req9_id, users[4].id, None, "COMPLETED", 160, 160, 150)
        add_task("VERIFY", req9_id, users[5].id, None, "COMPLETED", 150, 150, 130)
        add_task("DELIVER", req9_id, users[3].id, None, "COMPLETED", 130, 130, 100)

        db.session.commit()
        print("Database seeded successfully with all roles, branches and mock requests!")

if __name__ == '__main__':
    seed_data()
