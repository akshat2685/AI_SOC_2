// ==============================================================================
// AI SOC INTELLIGENCE ENGINE (EDYSOR-X) - PHASE 2 MIGRATION
// Neo4j Knowledge Graph Expansion (Constraints and Indexes)
// O(V+E) optimization structure
// ==============================================================================

// Create Uniqueness Constraints for O(1) node lookups
CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE;
CREATE CONSTRAINT device_id_unique IF NOT EXISTS FOR (d:Device) REQUIRE d.id IS UNIQUE;
CREATE CONSTRAINT ip_address_unique IF NOT EXISTS FOR (i:IP_Address) REQUIRE i.ip IS UNIQUE;
CREATE CONSTRAINT domain_unique IF NOT EXISTS FOR (d:Domain) REQUIRE d.domain IS UNIQUE;
CREATE CONSTRAINT hash_unique IF NOT EXISTS FOR (h:Hash) REQUIRE h.hash IS UNIQUE;
CREATE CONSTRAINT malware_id_unique IF NOT EXISTS FOR (m:Malware) REQUIRE m.id IS UNIQUE;
CREATE CONSTRAINT vuln_cve_unique IF NOT EXISTS FOR (v:Vulnerability) REQUIRE v.cve IS UNIQUE;
CREATE CONSTRAINT threat_actor_name_unique IF NOT EXISTS FOR (t:ThreatActor) REQUIRE t.name IS UNIQUE;
CREATE CONSTRAINT campaign_name_unique IF NOT EXISTS FOR (c:Campaign) REQUIRE c.name IS UNIQUE;
CREATE CONSTRAINT technique_id_unique IF NOT EXISTS FOR (t:Technique) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT tactic_id_unique IF NOT EXISTS FOR (t:Tactic) REQUIRE t.id IS UNIQUE;

// Create Indexes for property searches
CREATE INDEX user_name_idx IF NOT EXISTS FOR (u:User) ON (u.name);
CREATE INDEX device_hostname_idx IF NOT EXISTS FOR (d:Device) ON (d.hostname);
CREATE INDEX malware_name_idx IF NOT EXISTS FOR (m:Malware) ON (m.name);
CREATE INDEX threat_actor_alias_idx IF NOT EXISTS FOR (t:ThreatActor) ON (t.aliases);

// ------------------------------------------------------------------------------
// Relationship Schema Blueprint (Documented for Application Layer)
// 
// (User)-[:OWNS|USES]->(Device)
// (Device)-[:HAS_IP]->(IP_Address)
// (IP_Address)-[:USED_BY|RESOLVES_TO]->(Domain)
// (IP_Address)-[:ASSOCIATED_WITH]->(ThreatActor)
// (Malware)-[:EXPLOITS]->(Vulnerability)
// (Malware)-[:USES_TECHNIQUE]->(Technique)
// (Technique)-[:BELONGS_TO_TACTIC]->(Tactic)
// (ThreatActor)-[:CONDUCTS]->(Campaign)
// (Campaign)-[:TARGETS]->(Device|User)
// ------------------------------------------------------------------------------
