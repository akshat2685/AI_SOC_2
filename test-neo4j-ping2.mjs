import neo4j from 'neo4j-driver';
const driver = neo4j.driver(process.env.NEO4J_URI, neo4j.auth.basic(process.env.NEO4J_USERNAME, process.env.NEO4J_PASSWORD));
const session = driver.session();
session.run('MATCH (n) RETURN count(n) AS count')
  .then(res => { console.log('Count:', res.records[0].get('count').toNumber()); session.close(); driver.close(); })
  .catch(e => { console.log('Error', e); session.close(); driver.close(); });
