"""
Action Decision Prompt Builder

Constructs comprehensive prompts for the Action Agent to make informed decisions
about the robot's next action based on current assessment state, conversation context,
and phase-specific criteria.
"""

from typing import Dict, Optional, List


def build_action_decision_prompt(
    phase: int,
    assessment: Dict[str, str],
    comfort_assessment: Optional[Dict[str, str]],
    conversation_history: List[Dict],
    turn_number: int,
    phase_turn_number: int,
    situation_context: str = ""
) -> str:
    """
    Build comprehensive prompt for Action Agent decision-making.
    
    Args:
        phase: Current phase (1 or 2)
        assessment: Phase 1 assessment data
        comfort_assessment: Optional Phase 2 comfort assessment data
        conversation_history: Recent conversation exchanges
        turn_number: Overall turn number
        phase_turn_number: Turn number within current phase
        situation_context: Disaster situation description
        
    Returns:
        Complete prompt string for Action Agent
    """
    
    # Load base action prompt
    try:
        with open('prompts/action_prompt.txt', 'r', encoding='utf-8') as f:
            base_prompt = f.read()
    except FileNotFoundError:
        base_prompt = _get_default_action_prompt()
    
    prompt_parts = [base_prompt]
    
    # Add situation context if available
    if situation_context:
        prompt_parts.append(f"\n{'='*80}")
        prompt_parts.append("DISASTER SITUATION CONTEXT:")
        prompt_parts.append(f"{'='*80}")
        prompt_parts.append(situation_context)
    
    # Add current state information
    prompt_parts.append(f"\n{'='*80}")
    prompt_parts.append("CURRENT STATE:")
    prompt_parts.append(f"{'='*80}")
    prompt_parts.append(f"Phase: {phase} ({'Assessment' if phase == 1 else 'Comfort & Special Needs'})")
    prompt_parts.append(f"Total Turn Number: {turn_number}")
    prompt_parts.append(f"Phase Turn Number: {phase_turn_number}")
    
    # Add Phase 1 assessment
    prompt_parts.append(f"\n{'='*80}")
    prompt_parts.append("PHASE 1 ASSESSMENT (Safety & Injuries):")
    prompt_parts.append(f"{'='*80}")
    
    if assessment:
        for key, value in assessment.items():
            if key not in ['priority', 'gps_location']:  # Exclude internal fields
                status_indicator = "✓" if value and value != "unknown" else "?"
                prompt_parts.append(f"{status_indicator} {key}: {value}")
    else:
        prompt_parts.append("(No Phase 1 data available)")
    
    # Calculate assessment completion
    critical_fields = ["injuries", "breathing", "immediate_danger", "can_walk", "stuck_trapped", "consciousness"]
    assessed_fields = [f for f in critical_fields if assessment.get(f, "unknown") != "unknown"]
    completion_pct = (len(assessed_fields) / len(critical_fields)) * 100 if assessment else 0
    prompt_parts.append(f"\nPhase 1 Completion: {completion_pct:.0f}% ({len(assessed_fields)}/{len(critical_fields)} critical fields)")
    
    # Add Phase 2 assessment if in Phase 2
    if phase == 2 and comfort_assessment:
        prompt_parts.append(f"\n{'='*80}")
        prompt_parts.append("PHASE 2 ASSESSMENT (Medical & Special Needs):")
        prompt_parts.append(f"{'='*80}")
        
        for key, value in comfort_assessment.items():
            status_indicator = "✓" if value and value != "unknown" else "?"
            prompt_parts.append(f"{status_indicator} {key}: {value}")
    
    # Add recent conversation history
    if conversation_history:
        prompt_parts.append(f"\n{'='*80}")
        prompt_parts.append("RECENT CONVERSATION (Last 3 exchanges):")
        prompt_parts.append(f"{'='*80}")
        
        for entry in conversation_history:
            # Handle both 'type' and 'role' keys for compatibility
            role = entry.get('type') or entry.get('role', 'unknown')
            role_label = "🤖 Robot" if role == "robot" else "👤 Victim"
            content_preview = entry['content'][:150] + "..." if len(entry['content']) > 150 else entry['content']
            prompt_parts.append(f"{role_label}: {content_preview}")
    
    # Add phase-specific decision criteria
    if phase == 1:
        prompt_parts.append(_get_phase_1_decision_criteria(assessment, assessed_fields))
    else:
        prompt_parts.append(_get_phase_2_decision_criteria(assessment, comfort_assessment))
    
    # Add output format instructions
    prompt_parts.append(f"\n{'='*80}")
    prompt_parts.append("YOUR DECISION (JSON FORMAT):")
    prompt_parts.append(f"{'='*80}")
    prompt_parts.append("""
You MUST respond with ONLY a valid JSON object (no markdown fences, no explanation):

{
  "primary_action": "continue_conversation" | "transition_to_phase_2" | "evacuate_immediately" | "abort_and_alert" | "complete",
  "alert_command_center": true | false,
  "urgency_level": "routine" | "priority" | "critical" | "emergency",
  "reasoning": "Brief justification for your decision (1-2 sentences)",
  "next_phase": 2 | null,
  "specialized_equipment_needed": [] | ["stretcher", "cutting_tools", "medical_supplies", etc.]
}

Respond with ONLY the JSON object. Do not include any other text.
""")
    
    return "\n".join(prompt_parts)


def _get_phase_1_decision_criteria(assessment: Dict, assessed_fields: List[str]) -> str:
    """Get Phase 1 specific decision criteria"""
    
    criteria = [f"\n{'='*80}"]
    criteria.append("PHASE 1 DECISION CRITERIA:")
    criteria.append(f"{'='*80}")
    
    # Check for immediate danger
    immediate_danger = assessment.get("immediate_danger", "unknown")
    can_walk = assessment.get("can_walk", "unknown")
    
    if immediate_danger and "yes" in immediate_danger.lower():
        criteria.append("\n🚨 IMMEDIATE DANGER DETECTED:")
        if can_walk and "yes" in can_walk.lower():
            criteria.append("   ✓ Victim CAN walk")
            criteria.append("   → RECOMMENDATION: evacuate_immediately")
            criteria.append("   → Alert command center with urgency: critical")
        else:
            criteria.append("   ✗ Victim CANNOT walk or mobility unknown")
            criteria.append("   → RECOMMENDATION: abort_and_alert")
            criteria.append("   → Leave area, alert command center for specialized rescue")
            criteria.append("   → Equipment needed: stretcher, rescue team")
    else:
        criteria.append("\n✅ No immediate danger detected")
        
        # Check for mid-assessment evacuation potential
        injuries = assessment.get("injuries", "unknown")
        breathing = assessment.get("breathing", "unknown")
        consciousness = assessment.get("consciousness", "unknown")
        stuck_trapped = assessment.get("stuck_trapped", "unknown")
        
        can_evacuate_early = (
            can_walk and "yes" in can_walk.lower() and
            (injuries == "no" or (injuries != "unknown" and "minor" in injuries.lower())) and
            breathing and "yes" in breathing.lower() and
            consciousness and "conscious" in consciousness.lower() and
            (stuck_trapped == "no" or "no" in str(stuck_trapped).lower())
        )
        
        if can_evacuate_early:
            criteria.append("\n🏃 MID-ASSESSMENT EVACUATION CANDIDATE:")
            criteria.append("   ✓ Victim can walk")
            criteria.append("   ✓ No severe injuries")
            criteria.append("   ✓ Breathing normally")
            criteria.append("   ✓ Conscious")
            criteria.append("   ✓ Not trapped")
            criteria.append("   → OPTION: evacuate_immediately (skip Phase 2)")
            criteria.append("   → RATIONALE: Ambulatory, low-severity victim - efficient evacuation")
        
        # Check for Phase 2 transition factors
        emotional_state = assessment.get("emotional_state", "unknown")
        
        transition_factors = []
        if can_walk == "no" or "no" in str(can_walk).lower():
            transition_factors.append("Victim cannot walk (needs specialized rescue)")
        if stuck_trapped and "yes" in str(stuck_trapped).lower():
            transition_factors.append("Victim is trapped")
        if injuries and injuries != "unknown" and injuries != "no":
            if "severe" in injuries.lower() or "broken" in injuries.lower() or "bleeding" in injuries.lower():
                transition_factors.append("Severe injuries present")
        if emotional_state and "stressed" in emotional_state.lower():
            transition_factors.append("High emotional distress")
        
        if transition_factors:
            criteria.append("\n➡️  PHASE 2 TRANSITION FACTORS:")
            for factor in transition_factors:
                criteria.append(f"   • {factor}")
            criteria.append("   → RECOMMENDATION: transition_to_phase_2")
            criteria.append("   → Victim needs emotional support and detailed medical info gathering")
    
    # Assessment completion check
    critical_fields = ["injuries", "breathing", "immediate_danger", "can_walk", "stuck_trapped", "consciousness"]
    completion_pct = (len(assessed_fields) / len(critical_fields)) * 100
    
    criteria.append(f"\n📊 ASSESSMENT STATUS:")
    criteria.append(f"   Progress: {completion_pct:.0f}% complete")
    
    if completion_pct < 100:
        unknown_fields = [f for f in critical_fields if assessment.get(f, "unknown") == "unknown"]
        criteria.append(f"   Unknown fields: {', '.join(unknown_fields)}")
        criteria.append("   → If no emergency: continue_conversation to gather remaining data")
    else:
        criteria.append("   ✓ Assessment complete - make final decision (evacuate or transition)")
    
    return "\n".join(criteria)


def _get_phase_2_decision_criteria(assessment: Dict, comfort_assessment: Optional[Dict]) -> str:
    """Get Phase 2 specific decision criteria"""
    
    criteria = [f"\n{'='*80}"]
    criteria.append("PHASE 2 DECISION CRITERIA:")
    criteria.append(f"{'='*80}")
    
    # Check for critical medical needs
    if comfort_assessment:
        emergency_med = comfort_assessment.get("emergency_medication", "unknown")
        allergies = comfort_assessment.get("allergies", "unknown")
        pregnant = comfort_assessment.get("pregnant", "unknown")
        
        critical_discoveries = []
        
        if emergency_med and emergency_med != "unknown" and emergency_med != "no":
            critical_discoveries.append(f"Emergency medication needed: {emergency_med}")
        
        if allergies and allergies != "unknown" and allergies != "no":
            critical_discoveries.append(f"Allergies identified: {allergies}")
        
        if pregnant and "yes" in str(pregnant).lower():
            critical_discoveries.append("Victim is pregnant")
        
        if critical_discoveries:
            criteria.append("\n⚠️  CRITICAL MEDICAL NEEDS DISCOVERED:")
            for discovery in critical_discoveries:
                criteria.append(f"   • {discovery}")
            criteria.append("   → RECOMMENDATION: alert_command_center = true")
            criteria.append("   → Urgency level: priority or critical")
            criteria.append("   → Action: continue_conversation (but escalate priority)")
    
    # Check victim mobility for early evacuation
    can_walk = assessment.get("can_walk", "unknown")
    
    if can_walk and "yes" in can_walk.lower():
        criteria.append("\n🏃 AMBULATORY VICTIM:")
        criteria.append("   • Victim can walk independently")
        
        if comfort_assessment:
            critical_fields = ["emergency_medication", "allergies", "age"]
            assessed_critical = [f for f in critical_fields if comfort_assessment.get(f, "unknown") != "unknown"]
            
            if len(assessed_critical) >= 2:  # At least 2 of 3 critical fields known
                criteria.append("   • Sufficient medical information gathered")
                criteria.append("   → OPTION: evacuate_immediately")
                criteria.append("   → RATIONALE: Remove ambulatory victim from danger zone")
            else:
                criteria.append("   • Still gathering critical medical information")
                criteria.append("   → RECOMMENDATION: continue_conversation")
        else:
            criteria.append("   → RECOMMENDATION: continue_conversation (gather medical needs)")
    else:
        criteria.append("\n🚑 NON-AMBULATORY VICTIM:")
        criteria.append("   • Victim cannot walk or is trapped")
        criteria.append("   • Must wait for specialized rescue")
        criteria.append("   → Continue gathering complete medical information")
        criteria.append("   → Provide emotional support during wait")
    
    # Check for deterioration signs
    criteria.append("\n🔍 MONITOR FOR DETERIORATION:")
    criteria.append("   Watch recent victim responses for:")
    criteria.append("   • New difficulty breathing")
    criteria.append("   • Increasing pain")
    criteria.append("   • Growing panic/confusion")
    criteria.append("   • Reduced responsiveness")
    criteria.append("   → If detected: urgency_level = emergency")
    
    # Phase 2 completion check
    if comfort_assessment:
        priority_fields = ["emergency_medication", "allergies", "age", "regular_medication"]
        assessed = [f for f in priority_fields if comfort_assessment.get(f, "unknown") != "unknown"]
        completion_pct = (len(assessed) / len(priority_fields)) * 100
        
        criteria.append(f"\n📊 COMFORT ASSESSMENT STATUS:")
        criteria.append(f"   Progress: {completion_pct:.0f}% complete")
        
        if completion_pct >= 100:
            criteria.append("   ✓ Phase 2 complete")
            criteria.append("   → RECOMMENDATION: primary_action = complete")
    
    return "\n".join(criteria)


def _get_default_action_prompt() -> str:
    """
    Fallback action prompt if file not found
    """
    return """You are the Action Decision Agent for a rescue robot.

Your role is to analyze the current situation and decide the robot's next action.

Consider all available information:
- Phase 1 Assessment (injuries, breathing, mobility, danger)
- Phase 2 Assessment (medical needs, allergies, special conditions)
- Recent conversation context
- Victim's emotional state

Make informed decisions prioritizing:
1. Immediate life safety (danger, breathing, consciousness)
2. Victim mobility (can they walk? are they trapped?)
3. Information completeness (critical unknowns?)
4. Efficiency (evacuate ambulatory victims quickly)

Your decision will determine whether the robot continues conversation, evacuates
the victim, transitions to the next phase, or aborts to alert command center.
"""
